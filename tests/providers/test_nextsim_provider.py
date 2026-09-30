from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

from core.contracts import LocalENUFrameRef
from core.environment import GridSpec, IceField, IceFieldData
from core.providers.common import open_netcdf
from core.providers.nextsim import NextSIMIceProviderAdapter, NextSIMNetCDFReader


@pytest.fixture
def nextsim_file(tmp_path: Path) -> Path:
    path = tmp_path / "nextsim_fixture.nc"
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
        dataset.createVariable("latitude", "f8", ("latitude",))[:] = [0.002, 0.001]
        dataset.createVariable("longitude", "f8", ("longitude",))[:] = [0.0, 0.001]
        concentration = dataset.createVariable("ice_concentration", "f8", ("time", "latitude", "longitude"), fill_value=-9999.0)
        thickness = dataset.createVariable("ice_thickness", "f8", ("time", "latitude", "longitude"), fill_value=-9999.0)
        velocity_u = dataset.createVariable("ice_u", "f8", ("time", "latitude", "longitude"), fill_value=-9999.0)
        velocity_v = dataset.createVariable("ice_v", "f8", ("time", "latitude", "longitude"), fill_value=-9999.0)
        concentration.units = "%"
        thickness.units = "cm"
        velocity_u.units = "cm/s"
        velocity_v.units = "cm/s"
        concentration[0] = [[80, 0], [np.nan, 120]]
        thickness[0] = [[100, 0], [50, 200]]
        velocity_u[0] = [[100, 200], [300, 400]]
        velocity_v[0] = [[-100, -200], [-300, -400]]
    return path


@pytest.fixture
def grid() -> GridSpec:
    frame = LocalENUFrameRef(frame_id="nextsim", origin_lat_deg=0.001, origin_lon_deg=0.0, crs_or_projection_identifier="enu")
    return GridSpec(frame=frame, resolution_m=100, x_min_m=-50, y_min_m=-50, x_max_m=150, y_max_m=150, width_cells=2, height_cells=2)


def test_reader_reads_ice_variables_and_time(nextsim_file: Path) -> None:
    reader = NextSIMNetCDFReader(nextsim_file)
    reader.load()
    try:
        variables = reader.read_surface_variables(0)
        assert variables["concentration"].shape == (2, 2)
        assert variables["thickness"][0, 0] == 100
        assert reader.read_valid_times() == (datetime(2025, 1, 1, 6, tzinfo=timezone.utc),)
        assert reader.read_issue_time() == datetime(2025, 1, 1, tzinfo=timezone.utc)
    finally:
        reader.close()


def test_adapter_outputs_ice_field_with_converted_units_and_metadata(nextsim_file: Path, grid: GridSpec) -> None:
    adapter = NextSIMIceProviderAdapter(nextsim_file, grid)
    adapter.load()
    try:
        field = adapter.convert_to_environment_field()
        assert isinstance(field, IceField)
        assert isinstance(field.data, IceFieldData)
        assert field.data.ice_concentration[0] == [0.8, 0.0]
        assert field.data.ice_thickness_m[0] == [1.0, 0.0]
        assert field.data.ice_velocity_east_mps[0] == [1.0, 2.0]
        assert field.data.ice_velocity_north_mps[0] == [-1.0, -2.0]
        assert field.metadata.source_id == "neXtSIM-F"
        assert field.metadata.native_resolution_m == 1000
        assert field.metadata.representation_resolution_m == 100
        assert field.metadata.time.issue_time == datetime(2025, 1, 1, tzinfo=timezone.utc)
        assert field.metadata.time.valid_time == datetime(2025, 1, 1, 6, tzinfo=timezone.utc)
        assert field.metadata.time.ingest_time == adapter.reader.ingest_time
    finally:
        adapter.reader.close()


def test_nan_is_none_and_no_risk_logic(nextsim_file: Path, grid: GridSpec) -> None:
    adapter = NextSIMIceProviderAdapter(nextsim_file, grid)
    adapter.load()
    try:
        field = adapter.convert_to_environment_field()
        assert field.data is not None
        assert field.data.ice_concentration[1][0] is None
        assert field.data.ice_thickness_m[1][0] == 0.5
    finally:
        adapter.reader.close()
    import core.providers.nextsim as nextsim
    assert not any(hasattr(nextsim, name) for name in ("POLARIS", "RIV", "Risk", "Planner"))
