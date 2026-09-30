from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

from core.contracts import LocalENUFrameRef
from core.environment import CurrentField, CurrentFieldData, GridSpec
from core.providers.common import open_netcdf
from core.providers.topaz5 import TOPAZ5CurrentProviderAdapter, TOPAZ5NetCDFReader


@pytest.fixture
def topaz5_file(tmp_path: Path) -> Path:
    path = tmp_path / "topaz5_fixture.nc"
    with open_netcdf(path, "w") as dataset:
        dataset.createDimension("time", 2)
        dataset.createDimension("latitude", 2)
        dataset.createDimension("longitude", 2)
        dataset.native_resolution_m = 3000.0
        time = dataset.createVariable("time", "f8", ("time",))
        time.units = "hours since 2025-01-01 00:00:00"
        time[:] = [1, 2]
        issue = dataset.createVariable("forecast_reference_time", "f8")
        issue.units = "hours since 2025-01-01 00:00:00"
        issue.assignValue(0)
        dataset.createVariable("lat", "f8", ("latitude",))[:] = [0.002, 0.001]
        dataset.createVariable("lon", "f8", ("longitude",))[:] = [0.0, 0.001]
        uo = dataset.createVariable("uo", "f8", ("time", "latitude", "longitude"), fill_value=-9999.0)
        vo = dataset.createVariable("vo", "f8", ("time", "latitude", "longitude"), fill_value=-9999.0)
        uo.units = "cm/s"
        vo.units = "cm/s"
        uo[0] = [[100, 200], [np.nan, 400]]
        vo[0] = [[-100, -200], [-300, -400]]
        uo[1] = [[500, 600], [700, 800]]
        vo[1] = [[900, 1000], [1100, 1200]]
    return path


@pytest.fixture
def grid() -> GridSpec:
    frame = LocalENUFrameRef(frame_id="topaz", origin_lat_deg=0.001, origin_lon_deg=0.0, crs_or_projection_identifier="enu")
    return GridSpec(frame=frame, resolution_m=100, x_min_m=-50, y_min_m=-50, x_max_m=150, y_max_m=150, width_cells=2, height_cells=2)


def test_reader_aliases_units_and_time(topaz5_file: Path) -> None:
    reader = TOPAZ5NetCDFReader(topaz5_file)
    reader.load()
    try:
        assert reader.read_coordinates()[0].tolist() == pytest.approx([0.002, 0.001])
        assert reader.read_valid_times() == (datetime(2025, 1, 1, 1, tzinfo=timezone.utc), datetime(2025, 1, 1, 2, tzinfo=timezone.utc))
        uo, vo, units = reader.read_current_components(0)
        assert units == "cm/s"
        assert uo[0, 0] == 100 and vo[1, 1] == -400
    finally:
        reader.close()


def test_adapter_outputs_current_field_and_converts_cm_per_s(topaz5_file: Path, grid: GridSpec) -> None:
    adapter = TOPAZ5CurrentProviderAdapter(topaz5_file, grid)
    adapter.load()
    try:
        field = adapter.convert_to_environment_field()
        assert isinstance(field, CurrentField)
        assert isinstance(field.data, CurrentFieldData)
        assert field.data.current_east_mps[0] == [1.0, 2.0]
        assert field.data.current_north_mps[0] == [-1.0, -2.0]
        assert field.metadata.source_id == "TOPAZ5"
        assert field.metadata.native_resolution_m == 3000
        assert field.metadata.representation_resolution_m == 100
        assert field.metadata.time.issue_time == datetime(2025, 1, 1, tzinfo=timezone.utc)
        assert field.metadata.time.valid_time == datetime(2025, 1, 1, 1, tzinfo=timezone.utc)
        assert field.metadata.time.ingest_time == adapter.reader.ingest_time
    finally:
        adapter.reader.close()


def test_nan_is_none_and_missing_component_fails(tmp_path: Path, grid: GridSpec) -> None:
    path = tmp_path / "missing_vo.nc"
    with open_netcdf(path, "w") as dataset:
        dataset.createDimension("time", 1); dataset.createDimension("latitude", 2); dataset.createDimension("longitude", 2)
        time = dataset.createVariable("time", "f8", ("time",)); time.units = "hours since 2025-01-01"; time[:] = [0]
        dataset.createVariable("latitude", "f8", ("latitude",))[:] = [0.001, 0]
        dataset.createVariable("longitude", "f8", ("longitude",))[:] = [0, 0.001]
        dataset.createVariable("uo", "f8", ("time", "latitude", "longitude"))[:] = np.nan
    adapter = TOPAZ5CurrentProviderAdapter(path, grid); adapter.load()
    try:
        with pytest.raises(ValueError, match="vo"):
            adapter.convert_to_environment_field()
    finally:
        adapter.reader.close()

    import core.providers.topaz5 as topaz5
    assert not any(hasattr(topaz5, name) for name in ("Risk", "Planner", "Route"))
