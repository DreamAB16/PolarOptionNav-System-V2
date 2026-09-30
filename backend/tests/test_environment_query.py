from datetime import datetime, timezone
from math import hypot

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app import routes
from core.models import BathymetryState, CurrentState, Position, SeaIceState, WaveState, WindState
from services.environment_service import EnvironmentQueryService, EnvironmentService, EnvironmentTimeManager


UTC = timezone.utc


class FakeProvider:
    def __init__(self, layer_id: str, *, fail: bool = False) -> None:
        self.layer_id = layer_id
        self.source_name = f"test-{layer_id}"
        self.fail = fail
        self.calls = 0

    def get_metadata(self) -> dict[str, object]:
        return {"provider": self.layer_id, "source": self.source_name, "status": "ready"}

    def get_available_layers(self) -> list[dict[str, str]]:
        return [{"id": self.layer_id, "name": self.layer_id, "status": "ready"}]

    def query(self, *args: object) -> object:
        self.calls += 1
        if self.fail:
            raise ValueError("Point is outside data coverage.")
        if self.layer_id == "bathymetry":
            latitude, longitude = args
            return BathymetryState(
                latitude=float(latitude),
                longitude=float(longitude),
                depth=1250,
                timestamp=datetime(2025, 1, 1, tzinfo=UTC),
                source=self.source_name,
            )

        position, requested = args
        assert isinstance(position, Position)
        assert isinstance(requested, datetime)
        hour = requested.replace(minute=0, second=0, microsecond=0)
        if self.layer_id == "ice":
            matched = requested.replace(hour=12, minute=0, second=0, microsecond=0)
            return SeaIceState(
                latitude=position.latitude,
                longitude=position.longitude,
                timestamp=matched,
                concentration=0.8,
                thickness=1.4,
                drift_u=0.03,
                drift_v=0.04,
                source=self.source_name,
            )
        if self.layer_id == "wind":
            matched = hour.replace(hour=(hour.hour // 3) * 3)
            return WindState(
                latitude=position.latitude,
                longitude=position.longitude,
                timestamp=matched,
                matched_time=matched,
                u10=3,
                v10=4,
                wind_speed=5,
                wind_direction_math=53.13,
                wind_direction_meteorological=216.87,
                source=self.source_name,
            )
        if self.layer_id == "current":
            return CurrentState(
                timestamp=hour,
                latitude=position.latitude,
                longitude=position.longitude,
                vxo=0.1,
                vyo=0.2,
                current_east=0.12,
                current_north=0.16,
                current_speed=0.2,
                current_direction_to=36.87,
                source=self.source_name,
            )
        if self.layer_id == "wave":
            return WaveState(
                timestamp=hour,
                requested_time=requested,
                matched_time=hour,
                latitude=position.latitude,
                longitude=position.longitude,
                wave_height=2.5,
                wave_period=8,
                wave_direction_from=315,
                source=self.source_name,
            )
        raise AssertionError(f"unexpected provider: {self.layer_id}")


class FakeRasterProvider:
    def close(self) -> None:
        return None


def providers(*, failing_layer: str | None = None) -> list[FakeProvider]:
    return [
        FakeProvider(layer, fail=layer == failing_layer)
        for layer in ("bathymetry", "ice", "wind", "current", "wave")
    ]


@pytest.mark.parametrize("month", [2, 8])
def test_complete_query_returns_all_five_environment_components(month: int) -> None:
    values = providers()
    service = EnvironmentQueryService(values, EnvironmentTimeManager())
    requested = datetime(2025, month, 15, 12, tzinfo=UTC)

    state = service.query(80, 120, requested)

    assert state.requested_time == requested
    assert state.depth == 1250
    assert state.ice.available and state.wind.available
    assert state.current.available and state.wave.available
    assert state.ice.velocity.speed == pytest.approx(hypot(0.03, 0.04))
    assert state.sources.model_dump() == {
        "bathymetry": "test-bathymetry",
        "ice": "test-ice",
        "wind": "test-wind",
        "current": "test-current",
        "wave": "test-wave",
    }


def test_provider_matched_times_are_preserved_and_result_is_cached() -> None:
    values = providers()
    service = EnvironmentQueryService(values, EnvironmentTimeManager())
    requested = datetime(2025, 8, 15, 13, 30, tzinfo=UTC)

    first = service.query(80, 30, requested)
    second = service.query(80, 30, requested)

    assert first.wind.matched_time.hour == 12
    assert first.current.matched_time.hour == 13
    assert first.wave.matched_time.hour == 13
    assert first.ice.matched_time.hour == 12
    assert second == first
    assert [provider.calls for provider in values] == [1, 1, 1, 1, 1]


def test_one_provider_nodata_does_not_fail_the_complete_query() -> None:
    service = EnvironmentQueryService(providers(failing_layer="ice"), EnvironmentTimeManager())

    state = service.query(40, 10, datetime(2025, 2, 15, 12, tzinfo=UTC))

    assert state.ice.available is False
    assert state.ice.reason == "out_of_coverage"
    assert state.depth == 1250
    assert state.wind.available and state.current.available and state.wave.available


def test_batch_api_returns_100_results_and_rejects_more_than_500(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_service = EnvironmentService(
        providers=providers(),
        ice_raster_provider=FakeRasterProvider(),
    )
    monkeypatch.setattr(routes, "environment_service", fake_service)
    client = TestClient(app)
    single = client.get(
        "/api/environment/query",
        params={"lat": 80, "lon": 30, "time": "2025-08-15T13:30:00Z"},
    )
    assert single.status_code == 200
    assert single.json()["wind"]["matched_time"] == "2025-08-15T12:00:00Z"
    assert single.json()["ice"]["available"] is True
    payload = {
        "time": "2025-08-15T13:30:00Z",
        "points": [
            {"id": f"p{index}", "lat": 70 + index / 1000, "lon": 30}
            for index in range(100)
        ],
    }

    response = client.post("/api/environment/query/batch", json=payload)

    assert response.status_code == 200
    assert len(response.json()["results"]) == 100
    assert response.json()["results"][0]["id"] == "p0"
    payload["points"] = [
        {"id": f"p{index}", "lat": 70, "lon": 30}
        for index in range(501)
    ]
    assert client.post("/api/environment/query/batch", json=payload).status_code == 400
