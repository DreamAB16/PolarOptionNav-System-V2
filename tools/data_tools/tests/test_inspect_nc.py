from pathlib import Path

import numpy as np

from tools.data_tools.inspect.check_dataset import check_dataset
from tools.data_tools.inspect.inspect_nc import inspect_nc, open_netcdf


def _create_ice_dataset(path: Path) -> None:
    with open_netcdf(path, "w", format="NETCDF4") as dataset:
        dataset.title = "Synthetic Arctic sea ice test fixture"
        dataset.createDimension("time", 2)
        dataset.createDimension("lat", 3)
        dataset.createDimension("lon", 4)

        time = dataset.createVariable("time", "f8", ("time",))
        time.standard_name = "time"
        time.units = "hours since 2025-02-01 00:00:00"
        time.calendar = "standard"
        time[:] = [0, 24]

        latitude = dataset.createVariable("latitude", "f4", ("lat",))
        latitude.standard_name = "latitude"
        latitude.units = "degrees_north"
        latitude[:] = [60, 75, 90]

        longitude = dataset.createVariable("longitude", "f4", ("lon",))
        longitude.standard_name = "longitude"
        longitude.units = "degrees_east"
        longitude[:] = [0, 60, 120, 180]

        projection_y = dataset.createVariable("y", "f4", ("lat",))
        projection_y.standard_name = "projection_y_coordinate"
        projection_y.axis = "Y"
        projection_y.units = "m"
        projection_y[:] = [-1000, 0, 1000]
        projection_x = dataset.createVariable("x", "f4", ("lon",))
        projection_x.standard_name = "projection_x_coordinate"
        projection_x.axis = "X"
        projection_x.units = "m"
        projection_x[:] = [-1500, -500, 500, 1500]

        concentration = dataset.createVariable(
            "ice_conc", "f4", ("time", "lat", "lon"), fill_value=-9999
        )
        concentration.units = "%"
        concentration[:] = np.arange(24, dtype=np.float32).reshape(2, 3, 4)


def test_nc_inspection_reports_structure_ranges_and_time(tmp_path: Path) -> None:
    path = tmp_path / "ice.nc"
    _create_ice_dataset(path)

    report = inspect_nc(path, dataset_type="ice")

    assert report["file"]["format"] == "NETCDF4"
    assert report["dimensions"]["lat"]["size"] == 3
    assert report["variables"]["ice_conc"]["units"] == "%"
    assert report["variables"]["ice_conc"]["min"] == 0
    assert report["variables"]["ice_conc"]["max"] == 23
    assert report["coordinate_ranges"]["latitude"]["min"] == 60
    assert report["coordinate_ranges"]["latitude"]["max"] == 90
    assert report["projected_coordinate_ranges"]["projection_x"]["max"] == 1500
    assert report["projected_coordinate_ranges"]["projection_y"]["min"] == -1000
    assert report["time_range"]["start"].startswith("2025-02-01")
    assert report["time_range"]["end"].startswith("2025-02-02")
    assert report["arctic_route_check"]["suitable_for_arctic_navigation"] is True


def test_generic_checker_registers_supported_type(tmp_path: Path) -> None:
    path = tmp_path / "ice.nc"
    _create_ice_dataset(path)

    report = check_dataset("ice", path)

    assert report["dataset_type"] == "ice"
    assert report["arctic_route_check"]["failures"] == []
