from datetime import datetime, timezone
from math import hypot
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from pyproj import Geod

from backend.app.main import app
from core.config.environment_config import get_dataset_path
from core.models import CurrentState, Position
from core.netcdf import open_netcdf
from services.environment_service.current import RealCurrentProvider


UTC = timezone.utc


def _write_current(path: Path, *, masked_corner: bool = False) -> None:
    with open_netcdf(path, "w") as dataset:
        dataset.createDimension("time", 2)
        dataset.createDimension("y", 2)
        dataset.createDimension("x", 2)
        time = dataset.createVariable("time", "f8", ("time",))
        time.units = "hours since 2025-02-15 12:00:00"
        time[:] = [0, 1]
        x = dataset.createVariable("x", "f8", ("x",))
        y = dataset.createVariable("y", "f8", ("y",))
        x[:] = [-1, 0]
        y[:] = [0, 1]
        vxo = dataset.createVariable("vxo", "f4", ("time", "y", "x"), fill_value=-1e14)
        vyo = dataset.createVariable("vyo", "f4", ("time", "y", "x"), fill_value=-1e14)
        vxo[:] = [[[0, 2], [2, 4]], [[10, 10], [10, 10]]]
        vyo[:] = 0
        if masked_corner:
            vxo[0, 0, 0] = vxo._FillValue


def test_topaz_coordinate_and_vector_rotation_are_geographically_valid() -> None:
    current_directory = get_dataset_path("current") / "raw"
    if not any(current_directory.glob("Copernicus_current_*.nc")):
        pytest.skip("TOPAZ5 dataset not available")
    provider = RealCurrentProvider(current_directory)
    try:
        lon, lat = provider.topaz_to_wgs84(-36.0, -43.0)
        assert lon == pytest.approx(-84.942901, abs=0.01)
        assert lat == pytest.approx(41.559, abs=1.0)
        with open_netcdf(current_directory / "Copernicus_current_20250215.nc") as dataset:
            assert lon == pytest.approx(float(dataset.variables["longitude"][0, 0]), abs=1e-4)
            assert lat == pytest.approx(float(dataset.variables["latitude"][0, 0]), abs=1e-4)
        x, y = provider.wgs84_to_topaz(lon, lat)
        assert (x, y) == pytest.approx((-36.0, -43.0), abs=1e-8)

        geod = Geod(ellps="WGS84")
        directions = []
        for longitude in (-160, -100, -40, 20, 80, 140):
            x_file, y_file = provider.wgs84_to_topaz(longitude, 75)
            lon0, lat0 = provider.topaz_to_wgs84(x_file, y_file)
            lon_x, lat_x = provider.topaz_to_wgs84(x_file + 0.01, y_file)
            expected_x_bearing = geod.inv(lon0, lat0, lon_x, lat_x)[0] % 360
            east_x, north_x = provider.geographic_components(longitude, 75, 1, 0)
            actual_x_bearing = (np.degrees(np.arctan2(east_x, north_x)) + 360) % 360
            assert actual_x_bearing == pytest.approx(expected_x_bearing, abs=1e-7)
            assert hypot(east_x, north_x) == pytest.approx(1, rel=1e-4)
            directions.append(actual_x_bearing)
        assert max(directions) - min(directions) > 100

        east, north = provider.geographic_components(30, 75, 1.2, -0.4)
        assert hypot(east, north) == pytest.approx(hypot(1.2, -0.4), rel=1e-4)
    finally:
        provider.close()


def test_bilinear_interpolation_time_tie_and_missing_date(tmp_path: Path) -> None:
    _write_current(tmp_path / "Copernicus_current_20250215.nc")
    provider = RealCurrentProvider(tmp_path)
    try:
        lon, lat = provider.topaz_to_wgs84(-0.5, 0.5)
        state = provider.query(Position(latitude=lat, longitude=lon), datetime(2025, 2, 15, 12, 30, tzinfo=UTC))
        assert isinstance(state, CurrentState)
        assert state.vxo == pytest.approx(2.0)
        assert state.timestamp.hour == 12  # exact tie deliberately chooses the earlier hour
        with pytest.raises(ValueError, match="No current data for requested date"):
            provider.query(Position(latitude=lat, longitude=lon), datetime(2025, 3, 1, tzinfo=UTC))
    finally:
        provider.close()


def test_fill_value_is_not_converted_to_still_water(tmp_path: Path) -> None:
    _write_current(tmp_path / "Copernicus_current_20250215.nc", masked_corner=True)
    provider = RealCurrentProvider(tmp_path)
    try:
        lon, lat = provider.topaz_to_wgs84(-0.5, 0.5)
        with pytest.raises(ValueError, match="No current data"):
            provider.query(Position(latitude=lat, longitude=lon), datetime(2025, 2, 15, 12, tzinfo=UTC))
    finally:
        provider.close()


def test_batch_keeps_invalid_points_local_and_api_contract() -> None:
    current_directory = get_dataset_path("current") / "raw"
    if not any(current_directory.glob("Copernicus_current_*.nc")):
        pytest.skip("TOPAZ5 dataset not available")
    provider = RealCurrentProvider(current_directory)
    try:
        result = provider.query_many(
            [("sea", Position(latitude=75, longitude=30)), ("land", Position(latitude=70, longitude=100))],
            datetime(2025, 8, 15, 12, 40, tzinfo=UTC),
        )
        assert result["matched_time"] == "2025-08-15T13:00:00Z"
        assert result["currents"][0]["available"] is True
        assert result["currents"][1]["available"] is False
    finally:
        provider.close()

    with TestClient(app) as client:
        single = client.get("/api/environment/current/query", params={"lat": 75, "lon": 30, "time": "2025-02-15T12:20:00Z"})
        field = client.post("/api/environment/current/field", json={"time": "2025-02-15T12:00:00Z", "points": [{"id": "sea", "lat": 75, "lon": 30}]})
        assert single.status_code == 200
        assert single.json()["timestamp"] == "2025-02-15T12:00:00Z"
        assert field.status_code == 200
        assert set(("latitude", "longitude", "current_east", "current_north")).issubset(field.json()["currents"][0])
