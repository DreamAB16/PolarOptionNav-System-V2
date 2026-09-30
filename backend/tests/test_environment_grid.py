from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app import routes
from core.models import BathymetryState, CurrentState, Position, SeaIceState, WaveState, WindState
from services.environment_service import EnvironmentGridBuilder, EnvironmentService, EnvironmentTimeManager


UTC = timezone.utc


class FakeProvider:
    def __init__(self, layer: str, fail: bool = False) -> None:
        self.layer = layer
        self.source_name = f"grid-{layer}"
        self.fail = fail
        self.calls = 0

    def get_metadata(self):
        return {"provider": self.layer, "status": "ready", "source": self.source_name}

    def get_available_layers(self):
        return [{"id": self.layer, "name": self.layer, "status": "ready"}]

    def query(self, *args):
        self.calls += 1
        if self.fail:
            raise ValueError("Point is outside data coverage.")
        if self.layer == "bathymetry":
            return BathymetryState(latitude=args[0], longitude=args[1], depth=1200, timestamp=datetime(2025, 1, 1, tzinfo=UTC), source=self.source_name)
        position, requested = args
        hour = requested.replace(minute=0, second=0, microsecond=0)
        if self.layer == "ice":
            return SeaIceState(latitude=position.latitude, longitude=position.longitude, timestamp=requested.replace(hour=12, minute=0, second=0, microsecond=0), concentration=.8, thickness=1.2, drift_u=.1, drift_v=.2, source=self.source_name)
        if self.layer == "wind":
            matched = requested.replace(hour=(requested.hour // 3) * 3, minute=0, second=0, microsecond=0)
            return WindState(latitude=position.latitude, longitude=position.longitude, timestamp=matched, matched_time=matched, u10=3, v10=4, wind_speed=5, wind_direction_math=0, wind_direction_meteorological=0, source=self.source_name)
        if self.layer == "current":
            return CurrentState(timestamp=hour, latitude=position.latitude, longitude=position.longitude, vxo=.1, vyo=.2, current_east=.1, current_north=.2, current_speed=.224, current_direction_to=26, source=self.source_name)
        return WaveState(timestamp=hour, requested_time=requested, matched_time=hour, latitude=position.latitude, longitude=position.longitude, wave_height=2, wave_period=8, wave_direction_from=45, source=self.source_name)


def make_service(failing: str | None = None):
    providers = [FakeProvider(name, name == failing) for name in ("bathymetry", "ice", "wind", "current", "wave")]
    return EnvironmentService(providers=providers, ice_raster_provider=type("Raster", (), {"close": lambda self: None})()), providers


def test_grid_cell_fuses_all_five_components_and_preserves_match_times():
    service, _ = make_service()
    builder = EnvironmentGridBuilder(service)
    cell = builder.query(80, 30, datetime(2025, 2, 15, 13, 30, tzinfo=UTC))
    assert cell.depth == 1200
    assert cell.ice.concentration == .8 and cell.ice.velocity is not None
    assert cell.wind.matched_time.hour == 12
    assert cell.current.matched_time.hour == 13
    assert cell.wave.matched_time.hour == 13


def test_grid_cache_and_nodata():
    service, providers = make_service(failing="ice")
    builder = EnvironmentGridBuilder(service)
    requested = datetime(2025, 2, 15, 12, tzinfo=UTC)
    first = builder.query(80, 30, requested)
    second = builder.query(80, 30, requested)
    assert first == second and first.ice.available is False
    assert [p.calls for p in providers] == [1, 1, 1, 1, 1]


def test_grid_batch_supports_1000_and_rejects_1001():
    service, _ = make_service()
    builder = EnvironmentGridBuilder(service)
    points = [(str(i), Position(latitude=80, longitude=30)) for i in range(1000)]
    assert len(builder.query_many(points, datetime(2025, 2, 15, 12, tzinfo=UTC))) == 1000
    with pytest.raises(ValueError):
        builder.query_many(points + [("x", points[0][1])], datetime(2025, 2, 15, 12, tzinfo=UTC))


def test_grid_rejects_coordinates_outside_wgs84_bounds():
    service, _ = make_service()
    builder = EnvironmentGridBuilder(service)
    requested = datetime(2025, 2, 15, 12, tzinfo=UTC)
    with pytest.raises(ValueError):
        builder.query(90.1, 30, requested)
    with pytest.raises(ValueError):
        builder.query(80, 180.1, requested)


def test_grid_api_single_and_metadata(monkeypatch):
    service, _ = make_service()
    monkeypatch.setattr(routes, "environment_service", service)
    monkeypatch.setattr(routes, "environment_grid", EnvironmentGridBuilder(service))
    client = TestClient(app)
    response = client.get("/api/environment/grid/query", params={"lat": 80, "lon": 30, "time": "2025-02-15T13:30:00Z"})
    assert response.status_code == 200
    body = response.json()
    assert body["depth"] == 1200
    assert body["ice"]["available"] is True
    assert body["wind"]["matched_time"].endswith("12:00:00Z")
    assert client.get("/api/environment/grid").json()["crs"] == "EPSG:4326"
