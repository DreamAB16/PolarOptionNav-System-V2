from pathlib import Path

import numpy as np

from core.netcdf import open_netcdf
from tools.data_tools.preprocess.preprocess_copernicus_ice import (
    main,
    preprocess_copernicus_ice,
    validate_processed_copernicus_ice,
)


def create_source(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open_netcdf(path, "w", format="NETCDF4") as dataset:
        dataset.createDimension("time", 1)
        dataset.createDimension("latitude", 3)
        dataset.createDimension("longitude", 4)
        time = dataset.createVariable("time", "f8", ("time",))
        time.standard_name = "time"
        time.units = "hours since 2025-02-15 00:00:00"
        time[:] = [12]
        latitude = dataset.createVariable("latitude", "f8", ("latitude",))
        latitude.standard_name = "latitude"
        latitude.units = "degrees_north"
        latitude[:] = [60, 75, 90]
        longitude = dataset.createVariable("longitude", "f8", ("longitude",))
        longitude.standard_name = "longitude"
        longitude.units = "degrees_east"
        longitude[:] = [-180, -60, 60, 180]
        fields = {
            "siconc": ("sea_ice_area_fraction", "Sea Ice Concentration", "1", 0.8),
            "sithick": ("sea_ice_thickness", "Sea Ice Thickness", "m", 1.4),
            "siconc_my": ("sea_ice_classification", "Multi-year Ice", "1", 0.6),
            "siconc_young": ("sea_ice_classification", "Young Ice", "1", 0.2),
            "vxsi": ("eastward_sea_ice_velocity", "Eastward Ice Velocity", "m s-1", 0.1),
            "vysi": ("northward_sea_ice_velocity", "Northward Ice Velocity", "m s-1", -0.1),
            "sisnthick": ("surface_snow_thickness", "Surface Snow Thickness", "m", 0.3),
        }
        for name, (standard_name, long_name, units, value) in fields.items():
            variable = dataset.createVariable(
                name,
                "f8",
                ("time", "latitude", "longitude"),
                fill_value=np.nan,
            )
            variable.standard_name = standard_name
            variable.long_name = long_name
            variable.units = units
            variable[:] = value


def test_preprocess_preserves_values_and_compresses(tmp_path: Path) -> None:
    source = tmp_path / "raw" / "arctic_ice_20250215.nc"
    output = tmp_path / "processed" / "arctic_ice_20250215.nc"
    create_source(source)

    report = preprocess_copernicus_ice(source, output)

    assert report.output == output.resolve()
    assert report.grid_size == {"latitude": 3, "longitude": 4}
    assert report.spatial_range["latitude"] == (60.0, 90.0)
    with open_netcdf(output) as dataset:
        assert set(report.variables) == {
            "siconc", "sithick", "siconc_my", "siconc_young", "vxsi", "vysi", "sisnthick"
        }
        assert float(dataset.variables["siconc"][0, 1, 1]) == np.float32(0.8)
        assert dataset.variables["siconc"].dtype == np.dtype("float32")
        assert dataset.variables["siconc"].filters()["zlib"] is True
        assert dataset.variables["siconc"].filters()["complevel"] == 4
    validation = validate_processed_copernicus_ice(source, output)
    assert validation.date == "20250215"
    assert validation.fill_values_preserved is True


def test_cli_accepts_input_and_output(tmp_path: Path) -> None:
    source = tmp_path / "raw" / "arctic_ice_20250215.nc"
    output = tmp_path / "processed" / "arctic_ice_20250215.nc"
    create_source(source)

    assert main([str(source), "--output", str(output)]) == 0
    assert output.is_file()
