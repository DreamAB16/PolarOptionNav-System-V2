from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

from core.contracts import LocalENUFrameRef
from core.environment import GridSpec, WindField, WindFieldData
from core.providers.carra2 import CARRA2NetCDFReader, CARRA2WindProviderAdapter
from core.providers.common import open_netcdf


@pytest.fixture
def carra2_file(tmp_path: Path) -> Path:
    path = tmp_path / "carra2_fixture.nc"
    with open_netcdf(path, "w") as dataset:
        dataset.createDimension("time", 2)
        dataset.createDimension("latitude", 2)
        dataset.createDimension("longitude", 3)
        dataset.native_resolution_m = 2500.0
        time = dataset.createVariable("time", "f8", ("time",))
        time.units = "hours since 2025-01-01 00:00:00"
        time.calendar = "standard"
        time[:] = [3, 6]
        issue = dataset.createVariable("forecast_reference_time", "f8")
        issue.units = "hours since 2025-01-01 00:00:00"
        issue.assignValue(0)
        latitude = dataset.createVariable("latitude", "f8", ("latitude",))
        longitude = dataset.createVariable("longitude", "f8", ("longitude",))
        latitude[:] = [0.0020068, 0.001]
        longitude[:] = [0.0, 0.001, 0.002]
        u10 = dataset.createVariable("u10", "f8", ("time", "latitude", "longitude"), fill_value=-9999.0)
        v10 = dataset.createVariable("v10", "f8", ("time", "latitude", "longitude"), fill_value=-9999.0)
        u10[0] = [[1, 2, 3], [4, np.nan, 6]]
        v10[0] = [[-1, -2, -3], [-4, -5, -6]]
        u10[1] = [[11, 12, 13], [14, 15, 16]]
        v10[1] = [[21, 22, 23], [24, 25, 26]]
    return path


@pytest.fixture
def grid() -> GridSpec:
    frame = LocalENUFrameRef(
        frame_id="carra2-test",
        origin_lat_deg=0.001,
        origin_lon_deg=0.0,
        crs_or_projection_identifier="test-local-enu",
    )
    return GridSpec(
        frame=frame,
        resolution_m=100,
        x_min_m=-50,
        y_min_m=-50,
        x_max_m=250,
        y_max_m=150,
        width_cells=3,
        height_cells=2,
    )


def test_reader_resolves_coordinates_and_reads_multi_time_components(carra2_file: Path) -> None:
    reader = CARRA2NetCDFReader(carra2_file)
    reader.load()
    try:
        latitude, longitude = reader.read_coordinates()
        valid_times = reader.read_valid_times()
        u10, v10 = reader.read_wind_components(1)
        assert latitude.tolist() == pytest.approx([0.0020068, 0.001])
        assert longitude.tolist() == pytest.approx([0.0, 0.001, 0.002])
        assert valid_times == (
            datetime(2025, 1, 1, 3, tzinfo=timezone.utc),
            datetime(2025, 1, 1, 6, tzinfo=timezone.utc),
        )
        assert u10[0, 0] == 11
        assert v10[1, 2] == 26
        assert reader.read_issue_time() == datetime(2025, 1, 1, tzinfo=timezone.utc)
    finally:
        reader.close()


@pytest.mark.parametrize(
    ("latitude_name", "longitude_name"),
    [("latitude", "longitude"), ("lat", "lon")],
)
def test_reader_accepts_coordinate_aliases(
    tmp_path: Path, latitude_name: str, longitude_name: str
) -> None:
    path = tmp_path / f"coordinates_{latitude_name}.nc"
    with open_netcdf(path, "w") as dataset:
        dataset.createDimension("time", 1)
        dataset.createDimension("y", 2)
        dataset.createDimension("x", 2)
        time = dataset.createVariable("time", "f8", ("time",))
        time.units = "hours since 2025-01-01 00:00:00"
        time[:] = [0]
        lat = dataset.createVariable(latitude_name, "f8", ("y",))
        lon = dataset.createVariable(longitude_name, "f8", ("x",))
        lat[:] = [1, 0]
        lon[:] = [0, 1]
        dataset.createVariable("u10", "f8", ("time", "y", "x"))[:] = 1
        dataset.createVariable("v10", "f8", ("time", "y", "x"))[:] = 2
    reader = CARRA2NetCDFReader(path)
    reader.load()
    try:
        assert [axis.size for axis in reader.read_coordinates()] == [2, 2]
        assert reader.read_wind_components(0)[0].shape == (2, 2)
    finally:
        reader.close()


def test_adapter_builds_wind_field_with_east_north_semantics_and_metadata(
    carra2_file: Path, grid: GridSpec
) -> None:
    adapter = CARRA2WindProviderAdapter(carra2_file, grid, time_index=1)
    adapter.load()
    try:
        field = adapter.convert_to_environment_field()
        assert isinstance(field, WindField)
        assert isinstance(field.data, WindFieldData)
        assert field.variable.value == "wind"
        assert field.data.wind_east_mps[0] == [11.0, 12.0, 13.0]
        assert field.data.wind_north_mps[0] == [21.0, 22.0, 23.0]
        assert field.grid is grid
        assert field.metadata.source_id == "CARRA2"
        assert field.metadata.native_resolution_m == 2500
        assert field.metadata.representation_resolution_m == grid.resolution_m
        assert field.metadata.time.issue_time == datetime(2025, 1, 1, tzinfo=timezone.utc)
        assert field.metadata.time.valid_time == datetime(2025, 1, 1, 6, tzinfo=timezone.utc)
        assert field.metadata.time.ingest_time == adapter.reader.ingest_time
        assert field.metadata.availability.value == "AVAILABLE"
        assert field.metadata.quality.uncertainty is None
        assert field.metadata.evidence.status.value == "UNKNOWN"
    finally:
        adapter.reader.close()


def test_nan_wind_values_become_none_and_outside_grid_stays_unknown(
    carra2_file: Path, grid: GridSpec
) -> None:
    adapter = CARRA2WindProviderAdapter(carra2_file, grid, time_index=0)
    adapter.load()
    try:
        field = adapter.convert_to_environment_field()
        assert field.data is not None
        assert field.data.wind_east_mps[1][1] is None
        assert field.data.wind_north_mps[1][1] is None
    finally:
        adapter.reader.close()

    outside_frame = LocalENUFrameRef(
        frame_id="outside",
        origin_lat_deg=50,
        origin_lon_deg=50,
        crs_or_projection_identifier="test-local-enu",
    )
    outside_grid = GridSpec(
        frame=outside_frame,
        resolution_m=100,
        x_min_m=0,
        y_min_m=0,
        x_max_m=200,
        y_max_m=200,
        width_cells=2,
        height_cells=2,
    )
    outside = CARRA2WindProviderAdapter(carra2_file, outside_grid)
    outside.load()
    try:
        unknown_field = outside.convert_to_environment_field()
        assert unknown_field.data is None
        assert unknown_field.metadata.availability.value == "MISSING"
    finally:
        outside.reader.close()


def test_missing_component_fails_and_provider_exports_no_planning_logic(
    tmp_path: Path, grid: GridSpec
) -> None:
    path = tmp_path / "missing_v10.nc"
    with open_netcdf(path, "w") as dataset:
        dataset.createDimension("time", 1)
        dataset.createDimension("latitude", 2)
        dataset.createDimension("longitude", 2)
        time = dataset.createVariable("time", "f8", ("time",))
        time.units = "hours since 2025-01-01 00:00:00"
        time[:] = [0]
        dataset.createVariable("latitude", "f8", ("latitude",))[:] = [0.001, 0]
        dataset.createVariable("longitude", "f8", ("longitude",))[:] = [0, 0.001]
        dataset.createVariable("u10", "f8", ("time", "latitude", "longitude"))[:] = 1

    adapter = CARRA2WindProviderAdapter(path, grid)
    adapter.load()
    try:
        with pytest.raises(ValueError, match="v10"):
            adapter.convert_to_environment_field()
    finally:
        adapter.reader.close()

    import core.providers.carra2 as carra2

    assert not any(hasattr(carra2, name) for name in ("Risk", "Planner", "Route"))
