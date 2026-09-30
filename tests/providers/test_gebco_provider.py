from pathlib import Path

import numpy as np
import pytest
from core.contracts import LocalENUFrameRef, TimeMetadata
from core.environment import GridSpec
from core.providers.gebco import BathymetryField, GEBCONetCDFReader, GEBCOProviderAdapter
from core.providers.common import open_netcdf


@pytest.fixture
def gebco_file(tmp_path: Path) -> Path:
    path = tmp_path / "gebco_fixture.nc"
    with open_netcdf(path, "w") as dataset:
        dataset.createDimension("lat", 2)
        dataset.createDimension("lon", 3)
        dataset.title = "GEBCO fixture"
        lat = dataset.createVariable("lat", "f8", ("lat",))
        lon = dataset.createVariable("longitude", "f8", ("lon",))
        lat[:] = [0.0020068, 0.001]
        lon[:] = [0.0, 0.001, 0.002]
        elevation = dataset.createVariable(
            "elevation", "f8", ("lat", "lon"), fill_value=-9999.0
        )
        elevation.standard_name = "height_above_mean_sea_level"
        elevation.units = "m"
        elevation[:] = [[-100.0, -5.0, 10.0], [-200.0, np.nan, -9999.0]]
    return path


@pytest.fixture
def grid() -> GridSpec:
    frame = LocalENUFrameRef(
        frame_id="gebco-test",
        origin_lat_deg=0.001,
        origin_lon_deg=0.0,
        crs_or_projection_identifier="test-local-enu",
    )
    return GridSpec(
        frame=frame,
        resolution_m=111.2,
        x_min_m=-55.6,
        y_min_m=-55.6,
        x_max_m=278.0,
        y_max_m=166.8,
        width_cells=3,
        height_cells=2,
    )


def test_reader_opens_netcdf_and_resolves_coordinate_names(gebco_file: Path) -> None:
    reader = GEBCONetCDFReader(gebco_file)
    reader.load()
    try:
        latitude, longitude = reader.read_coordinates()
        elevation = reader.read_elevation()
        assert latitude.tolist() == pytest.approx([0.0020068, 0.001])
        assert longitude.tolist() == pytest.approx([0.0, 0.001, 0.002])
        assert elevation.shape == (2, 3)
        assert reader.read_dataset_metadata()["title"] == "GEBCO fixture"
    finally:
        reader.close()


def test_adapter_converts_elevation_to_positive_down_depth(
    gebco_file: Path, grid: GridSpec
) -> None:
    adapter = GEBCOProviderAdapter(gebco_file, grid)
    adapter.load()
    try:
        field = adapter.convert_to_environment_field()
        assert isinstance(field, BathymetryField)
        assert field.data == [[100.0, 5.0, 0.0], [200.0, None, None]]
        assert field.depth_m is field.data
        assert field.grid is grid
    finally:
        adapter.reader.close()


def test_adapter_produces_shared_metadata_and_unknown_static_times(
    gebco_file: Path, grid: GridSpec
) -> None:
    adapter = GEBCOProviderAdapter(gebco_file, grid)
    adapter.load()
    try:
        metadata = adapter.read_metadata()
        assert metadata.source_id == "GEBCO fixture"
        assert metadata.native_resolution_m is not None
        assert metadata.representation_resolution_m == grid.resolution_m
        assert isinstance(metadata.time, TimeMetadata)
        assert metadata.time.issue_time is None
        assert metadata.time.valid_time is None
        assert metadata.time.ingest_time is None
        assert metadata.availability.value == "AVAILABLE"
        assert metadata.quality.uncertainty is None
        assert metadata.evidence.status.value == "UNKNOWN"
    finally:
        adapter.reader.close()


def test_all_missing_elevation_stays_none_and_availability_is_missing(
    tmp_path: Path, grid: GridSpec
) -> None:
    path = tmp_path / "all_missing.nc"
    with open_netcdf(path, "w") as dataset:
        dataset.createDimension("lat", 2)
        dataset.createDimension("lon", 3)
        lat = dataset.createVariable("latitude", "f8", ("lat",))
        lon = dataset.createVariable("lon", "f8", ("lon",))
        lat[:] = [0.0020068, 0.001]
        lon[:] = [0.0, 0.001, 0.002]
        elevation = dataset.createVariable(
            "elevation", "f8", ("lat", "lon"), fill_value=-9999.0
        )
        elevation.units = "m"
        elevation[:] = np.full((2, 3), -9999.0)

    adapter = GEBCOProviderAdapter(path, grid)
    adapter.load()
    try:
        field = adapter.convert_to_environment_field()
        assert field.data is None
        assert field.metadata.availability.value == "MISSING"
    finally:
        adapter.reader.close()


def test_enu_grid_is_sampled_into_local_row_column_order(
    gebco_file: Path, grid: GridSpec
) -> None:
    adapter = GEBCOProviderAdapter(gebco_file, grid)
    adapter.load()
    try:
        field = adapter.convert_to_environment_field()
        assert field.data[0] == [100.0, 5.0, 0.0]
        assert field.data[1] == [200.0, None, None]
    finally:
        adapter.reader.close()
