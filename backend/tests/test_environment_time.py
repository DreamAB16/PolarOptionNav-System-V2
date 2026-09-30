from datetime import datetime, timedelta, timezone

from core.models import EnvironmentQuery
from services.environment_service import EnvironmentService, EnvironmentTimeManager, MockIceProvider


def test_environment_time_manager_normalizes_time_builds_queries_and_advances() -> None:
    manager = EnvironmentTimeManager(
        simulation_time=datetime(2025, 2, 15, 12),
        time_step=timedelta(hours=1),
    )

    query = manager.make_query(75.0, 15.0)

    assert query == EnvironmentQuery(
        latitude=75.0,
        longitude=15.0,
        timestamp=datetime(2025, 2, 15, 12, tzinfo=timezone.utc),
    )
    assert manager.advance(2) == datetime(2025, 2, 15, 14, tzinfo=timezone.utc)
    assert manager.state().time_step_seconds == 3600


def test_environment_time_manager_controls_scenarios_and_playback() -> None:
    manager = EnvironmentTimeManager()

    manager.play()
    assert manager.state().is_playing is True
    manager.pause()
    assert manager.state().is_playing is False
    assert manager.set_scenario("summer") == datetime(2025, 8, 8, 0, tzinfo=timezone.utc)
    assert manager.next() == datetime(2025, 8, 8, 1, tzinfo=timezone.utc)
    assert manager.previous() == datetime(2025, 8, 8, 0, tzinfo=timezone.utc)
    assert manager.set_time(datetime(2025, 8, 15, 12)) == datetime(2025, 8, 15, 12, tzinfo=timezone.utc)
    assert manager.get_time() == datetime(2025, 8, 15, 12, tzinfo=timezone.utc)


def test_environment_service_uses_unified_query_for_ice_provider() -> None:
    manager = EnvironmentTimeManager(simulation_time=datetime(2025, 2, 15, 12, tzinfo=timezone.utc))
    service = EnvironmentService(providers=[MockIceProvider()], time_manager=manager)
    query = EnvironmentQuery(
        latitude=72.0,
        longitude=18.0,
        timestamp=datetime(2025, 2, 20, 8, tzinfo=timezone.utc),
    )

    result = service.query_ice(query)

    assert result.latitude == query.latitude
    assert result.longitude == query.longitude
    assert result.timestamp == query.timestamp
    assert result.source == "mock"


def test_environment_service_uses_simulation_time_for_undated_ice_tiles() -> None:
    class CapturingRaster:
        requested_time: object = None

        def get_tile(self, zoom, x, y, requested_time, time_index):
            self.requested_time = requested_time
            return b"png"

    manager = EnvironmentTimeManager(
        simulation_time=datetime(2025, 8, 15, 12, tzinfo=timezone.utc)
    )
    raster = CapturingRaster()
    service = EnvironmentService(
        providers=[MockIceProvider()],
        ice_raster_provider=raster,
        time_manager=manager,
    )

    assert service.get_ice_tile(2, 2, 0) == b"png"
    assert raster.requested_time == manager.simulation_time
