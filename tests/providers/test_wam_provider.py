from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

from core.contracts import LocalENUFrameRef
from core.environment import GridSpec, WaveField, WaveFieldData
from core.providers.common import open_netcdf
from core.providers.wam import WAMNetCDFReader, WAMWaveProviderAdapter


@pytest.fixture
def wam_file(tmp_path: Path) -> Path:
    path = tmp_path / "wam_fixture.nc"
    with open_netcdf(path, "w") as dataset:
        dataset.createDimension("time", 1)
        dataset.createDimension("latitude", 2)
        dataset.createDimension("longitude", 2)
        dataset.native_resolution_m = 1000.0
        time = dataset.createVariable("time", "f8", ("time",))
        time.units = "hours since 2025-01-01 00:00:00"
        time[:] = [6]
        issue = dataset.createVariable("forecast_reference_time", "f8")
        issue.units = "hours since 2025-01-01 00:00:00"
        issue.assignValue(0)
        dataset.createVariable("lat", "f8", ("latitude",))[:] = [0.002, 0.001]
        dataset.createVariable("lon", "f8", ("longitude",))[:] = [0.0, 0.001]
        height = dataset.createVariable("Hs", "f8", ("time", "latitude", "longitude"), fill_value=-9999.0)
        period = dataset.createVariable("Tp", "f8", ("time", "latitude", "longitude"), fill_value=-9999.0)
        direction = dataset.createVariable("direction", "f8", ("time", "latitude", "longitude"), fill_value=-9999.0)
        height.units = "cm"
        period.units = "s"
        direction.units = "degree"
        height[0] = [[100, 200], [np.nan, 400]]
        period[0] = [[10, 20], [30, 40]]
        direction[0] = [[0, 90], [180, 270]]
    return path


@pytest.fixture
def grid() -> GridSpec:
    frame = LocalENUFrameRef(frame_id="wam", origin_lat_deg=0.001, origin_lon_deg=0.0, crs_or_projection_identifier="enu")
    return GridSpec(frame=frame, resolution_m=100, x_min_m=-50, y_min_m=-50, x_max_m=150, y_max_m=150, width_cells=2, height_cells=2)


def test_reader_aliases_and_wave_variables(wam_file: Path) -> None:
    reader = WAMNetCDFReader(wam_file)
    reader.load()
    try:
        values = reader.read_wave_variables(0)
        assert values["height"].shape == (2, 2)
        assert values["period"][0, 0] == 10
        assert values["direction"][0, 1] == 90
        assert reader.read_valid_times() == (datetime(2025, 1, 1, 6, tzinfo=timezone.utc),)
        assert reader.read_issue_time() == datetime(2025, 1, 1, tzinfo=timezone.utc)
    finally:
        reader.close()


def test_adapter_outputs_wave_field_and_to_direction(wam_file: Path, grid: GridSpec) -> None:
    adapter = WAMWaveProviderAdapter(wam_file, grid)
    adapter.load()
    try:
        field = adapter.convert_to_environment_field()
        assert isinstance(field, WaveField)
        assert isinstance(field.data, WaveFieldData)
        assert field.data.wave_height_m[0] == [1.0, 2.0]
        assert field.data.wave_period_s[0] == [10.0, 20.0]
        assert field.data.wave_direction_rad[0] == pytest.approx([0.0, np.pi / 2])
        assert field.metadata.source_id == "WAM"
        assert field.metadata.direction_convention == "TO"
        assert field.metadata.native_resolution_m == 1000
        assert field.metadata.representation_resolution_m == 100
        assert field.metadata.time.issue_time == datetime(2025, 1, 1, tzinfo=timezone.utc)
        assert field.metadata.time.valid_time == datetime(2025, 1, 1, 6, tzinfo=timezone.utc)
        assert field.metadata.time.ingest_time == adapter.reader.ingest_time
    finally:
        adapter.reader.close()


def test_nan_is_none_and_missing_variable_fails(tmp_path: Path, grid: GridSpec) -> None:
    path = tmp_path / "missing_tp.nc"
    with open_netcdf(path, "w") as dataset:
        dataset.createDimension("time", 1); dataset.createDimension("latitude", 2); dataset.createDimension("longitude", 2)
        time = dataset.createVariable("time", "f8", ("time",)); time.units = "hours since 2025-01-01"; time[:] = [0]
        dataset.createVariable("latitude", "f8", ("latitude",))[:] = [0.001, 0]
        dataset.createVariable("longitude", "f8", ("longitude",))[:] = [0, 0.001]
        dataset.createVariable("Hs", "f8", ("time", "latitude", "longitude"))[:] = np.nan
        dataset.createVariable("direction", "f8", ("time", "latitude", "longitude"))[:] = 0
    adapter = WAMWaveProviderAdapter(path, grid); adapter.load()
    try:
        with pytest.raises(ValueError, match="period"):
            adapter.convert_to_environment_field()
    finally:
        adapter.reader.close()
    import core.providers.wam as wam
    assert not any(hasattr(wam, name) for name in ("Risk", "Planner", "Route"))
