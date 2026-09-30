from datetime import datetime, timezone
from pathlib import Path

from core.models import Position, WindState
from core.netcdf import open_netcdf
from services.environment_service import CARRA2WindProvider, RealWindProvider


def test_real_wind_provider_interpolates_and_matches_time(tmp_path: Path):
    path = tmp_path / "ERA5_wind_202502.nc"
    with open_netcdf(path, "w") as dataset:
        dataset.createDimension("time", 2)
        dataset.createDimension("latitude", 2)
        dataset.createDimension("longitude", 2)
        time = dataset.createVariable("time", "f8", ("time",))
        time.units = "hours since 2025-02-15 00:00:00"
        time[:] = [0, 1]
        latitude = dataset.createVariable("latitude", "f4", ("latitude",))
        latitude[:] = [70, 60]
        longitude = dataset.createVariable("longitude", "f4", ("longitude",))
        longitude[:] = [0, 10]
        u10 = dataset.createVariable("u10", "f4", ("time", "latitude", "longitude"))
        v10 = dataset.createVariable("v10", "f4", ("time", "latitude", "longitude"))
        u10[:] = [[[4, 4], [4, 4]], [[6, 6], [6, 6]]]
        v10[:] = [[[0, 0], [0, 0]], [[0, 0], [0, 0]]]

    provider = RealWindProvider(tmp_path)
    try:
        state = provider.query(Position(latitude=65, longitude=5), datetime(2025, 2, 15, 0, 31, tzinfo=timezone.utc))
        assert isinstance(state, WindState)
        assert state.u10 == 6
        assert state.wind_speed == 6
        assert state.wind_direction_meteorological == 270
        assert state.timestamp.hour == 1
    finally:
        provider.close()


def test_carra2_wind_provider_matches_time_and_converts_direction(tmp_path: Path):
    for kind, variable_name, value in (
        ("speed", "si10", 10.0),
        ("direction", "wdir10", 90.0),
    ):
        path = tmp_path / f"10m_wind_{kind}_202502.nc"
        with open_netcdf(path, "w") as dataset:
            dataset.createDimension("time", 2)
            dataset.createDimension("y", 3)
            dataset.createDimension("x", 3)
            valid_time = dataset.createVariable("valid_time", "f8", ("time",))
            valid_time.units = "hours since 2025-02-15 00:00:00"
            valid_time[:] = [12, 15]
            latitude = dataset.createVariable("latitude", "f4", ("y", "x"))
            longitude = dataset.createVariable("longitude", "f4", ("y", "x"))
            latitude[:] = [[79, 79, 79], [80, 80, 80], [81, 81, 81]]
            longitude[:] = [[29, 30, 31], [29, 30, 31], [29, 30, 31]]
            variable = dataset.createVariable(variable_name, "f4", ("time", "y", "x"))
            variable[:] = value

    provider = CARRA2WindProvider(tmp_path)
    try:
        state = provider.query(
            Position(latitude=80, longitude=30),
            datetime(2025, 2, 15, 13, tzinfo=timezone.utc),
        )
        assert isinstance(state, WindState)
        assert state.timestamp == datetime(2025, 2, 15, 12, tzinfo=timezone.utc)
        assert state.matched_time == state.timestamp
        assert state.wind_speed == 10
        assert state.wind_direction == 90
        assert state.wind_direction_meteorological == 90
        assert state.u10 == -10
        assert abs(state.v10) < 1e-10
        assert state.source == "CARRA2 Pan-Arctic"
    finally:
        provider.close()
