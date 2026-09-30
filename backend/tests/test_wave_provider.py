from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from core.config.environment_config import get_dataset_path
from core.models import Position, WaveState
from core.netcdf import open_netcdf
from services.environment_service import RealWaveProvider


UTC = timezone.utc


def _write_wave(path: Path, *, masked_corner: bool = False) -> None:
    with open_netcdf(path, "w") as dataset:
        dataset.createDimension("time", 2)
        dataset.createDimension("latitude", 2)
        dataset.createDimension("longitude", 2)
        time = dataset.createVariable("time", "f8", ("time",))
        time.units = "hours since 2025-02-15 12:00:00"
        time[:] = np.array([0, 1], dtype=np.float64)
        latitude = dataset.createVariable("latitude", "f8", ("latitude",))
        longitude = dataset.createVariable("longitude", "f8", ("longitude",))
        latitude[:] = np.array([60, 70], dtype=np.float64)
        longitude[:] = np.array([0, 10], dtype=np.float64)
        height = dataset.createVariable("VHM0", "f4", ("time", "latitude", "longitude"), fill_value=np.nan)
        period = dataset.createVariable("VTPK", "f4", ("time", "latitude", "longitude"), fill_value=np.nan)
        direction = dataset.createVariable("VMDR", "f4", ("time", "latitude", "longitude"), fill_value=np.nan)
        height[...] = np.array([[[1, 3], [1, 3]], [[5, 5], [5, 5]]], dtype=np.float32)
        period[...] = np.array([[[6, 8], [6, 8]], [[9, 9], [9, 9]]], dtype=np.float32)
        direction[...] = np.array([[[359, 1], [359, 1]], [[90, 90], [90, 90]]], dtype=np.float32)
        if masked_corner:
            height[0, 0, 0] = np.nan


def test_wave_interpolation_uses_circular_direction_and_earlier_time_tie(tmp_path: Path) -> None:
    _write_wave(tmp_path / "Copernicus_wave_20250215.nc")
    provider = RealWaveProvider(tmp_path)
    try:
        state = provider.query(
            Position(latitude=65, longitude=5),
            datetime(2025, 2, 15, 12, 30, tzinfo=UTC),
        )
        assert isinstance(state, WaveState)
        assert state.wave_height == pytest.approx(2)
        assert state.wave_period == pytest.approx(7)
        assert state.wave_direction_from == pytest.approx(0, abs=1e-6)
        assert state.matched_time.hour == 12
        assert state.requested_time.minute == 30
        scalar_state = provider.query(65, 5, datetime(2025, 2, 15, 12, 30, tzinfo=UTC))
        assert scalar_state.wave_direction_from == pytest.approx(0, abs=1e-6)
        with pytest.raises(ValueError, match="No wave data for requested date"):
            provider.query(Position(latitude=65, longitude=5), datetime(2025, 3, 1, tzinfo=UTC))
    finally:
        provider.close()


def test_wave_nodata_and_batch_unavailable_are_not_zero(tmp_path: Path) -> None:
    _write_wave(tmp_path / "Copernicus_wave_20250215.nc", masked_corner=True)
    provider = RealWaveProvider(tmp_path)
    try:
        with pytest.raises(ValueError, match="No wave data"):
            provider.query(Position(latitude=65, longitude=5), datetime(2025, 2, 15, 12, tzinfo=UTC))
        result = provider.query_many(
            [("masked", Position(latitude=65, longitude=5)), ("outside", Position(latitude=40, longitude=5))],
            datetime(2025, 2, 15, 12, tzinfo=UTC),
        )
        assert [item["available"] for item in result["waves"]] == [False, False]
        assert [item["reason"] for item in result["waves"]] == ["no_data", "out_of_coverage"]
    finally:
        provider.close()


def test_real_wave_files_and_api_contract() -> None:
    wave_directory = get_dataset_path("wave") / "raw"
    if not any(wave_directory.glob("Copernicus_wave_*.nc")):
        pytest.skip("WAM dataset not available")
    provider = RealWaveProvider(wave_directory)
    try:
        winter = provider.query(Position(latitude=80, longitude=30), datetime(2025, 2, 15, 12, 20, tzinfo=UTC))
        summer = provider.query(Position(latitude=80, longitude=30), datetime(2025, 8, 15, 12, 40, tzinfo=UTC))
        assert winter.matched_time == datetime(2025, 2, 15, 12, tzinfo=UTC)
        assert summer.matched_time == datetime(2025, 8, 15, 13, tzinfo=UTC)
        assert winter.wave_height >= 0 and summer.wave_height >= 0
        assert 0 <= winter.wave_direction_from < 360
    finally:
        provider.close()

    with TestClient(app) as client:
        single = client.get("/api/environment/wave/query", params={"lat": 80, "lon": 30, "time": "2025-02-15T12:20:00Z"})
        field = client.post("/api/environment/wave/field", json={
            "time": "2025-02-15T12:00:00Z",
            "points": [{"id": "sea", "lat": 80, "lon": 30}, {"id": "ice", "lat": 75, "lon": -30}],
        })
        assert single.status_code == 200
        assert set(("wave_height", "wave_period", "wave_direction_from", "requested_time", "matched_time")).issubset(single.json())
        assert field.status_code == 200
        assert field.json()["waves"][0]["available"] is True
        assert field.json()["waves"][1] == {
            "id": "ice", "available": False, "latitude": 75.0, "longitude": -30.0, "reason": "no_data"
        }
