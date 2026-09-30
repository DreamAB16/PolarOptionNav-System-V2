"""Inspect native-grid Copernicus TOPAZ5 surface-current NetCDF files."""

from __future__ import annotations

import argparse
from datetime import timezone
import json
from pathlib import Path

import numpy as np
from netCDF4 import num2date
from pyproj import CRS

from core.netcdf import open_netcdf


TOPAZ_PROJ4 = "+units=m +proj=stere +lon_0=-45 +lat_0=90 +k=1 +R=6378273 +no_defs"
SAMPLE_TARGETS = {
    "巴伦支海": (75.0, 35.0),
    "挪威海": (70.0, 5.0),
    "格陵兰海": (75.0, -5.0),
    "白令海峡": (66.0, -169.0),
    "加拿大北极": (75.0, -100.0),
}


def _attributes(variable: object) -> dict[str, object]:
    names = (
        "standard_name", "long_name", "units", "_FillValue", "missing_value",
        "valid_min", "valid_max", "grid_mapping", "scale_factor", "add_offset",
    )
    available = set(getattr(variable, "ncattrs")())
    get = getattr(variable, "getncattr")
    return {name: get(name) for name in names if name in available}


def _statistics(values: np.ma.MaskedArray) -> dict[str, float]:
    data = values.compressed().astype(np.float64)
    return {
        "min": float(np.min(data)),
        "max": float(np.max(data)),
        "mean": float(np.mean(data)),
        "median": float(np.median(data)),
    }


def inspect_current(path: str | Path) -> dict[str, object]:
    nc_path = Path(path)
    with open_netcdf(nc_path) as dataset:
        time_variable = dataset.variables["time"]
        times = list(num2date(
            time_variable[:], units=time_variable.units,
            calendar=getattr(time_variable, "calendar", "standard"),
            only_use_cftime_datetimes=False,
        ))
        times = [value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc) for value in times]
        noon_index = min(range(len(times)), key=lambda index: abs(times[index].hour - 12))
        vxo = np.ma.masked_invalid(np.ma.asarray(dataset.variables["vxo"][noon_index]))
        vyo = np.ma.masked_invalid(np.ma.asarray(dataset.variables["vyo"][noon_index]))
        combined_mask = np.ma.getmaskarray(vxo) | np.ma.getmaskarray(vyo)
        valid = ~combined_mask
        x_values = np.asarray(dataset.variables["x"][:], dtype=np.float64)
        y_values = np.asarray(dataset.variables["y"][:], dtype=np.float64)
        latitude = np.asarray(dataset.variables["latitude"][:], dtype=np.float64)
        longitude = np.asarray(dataset.variables["longitude"][:], dtype=np.float64)
        speed = np.ma.array(np.hypot(vxo.filled(np.nan), vyo.filled(np.nan)), mask=combined_mask)
        samples = []
        for name, (target_lat, target_lon) in SAMPLE_TARGETS.items():
            lat_scale = np.cos(np.deg2rad(target_lat))
            lon_delta = (longitude - target_lon + 180.0) % 360.0 - 180.0
            distance = (latitude - target_lat) ** 2 + (lon_delta * lat_scale) ** 2
            distance = np.where(valid, distance, np.inf)
            row, column = np.unravel_index(int(np.argmin(distance)), distance.shape)
            samples.append({
                "region": name,
                "time": times[noon_index].isoformat(),
                "latitude": float(latitude[row, column]),
                "longitude": float(longitude[row, column]),
                "vxo": float(vxo[row, column]),
                "vyo": float(vyo[row, column]),
                "grid_speed": float(speed[row, column]),
            })
        total = int(vxo.size)
        valid_count = int(np.count_nonzero(valid))
        speed_values = speed.compressed().astype(np.float64)
        grid_mapping = getattr(dataset.variables["vxo"], "grid_mapping", None)
        return {
            "file": {"path": str(nc_path.resolve()), "size_bytes": nc_path.stat().st_size, "format": dataset.data_model, "disk_format": dataset.disk_format},
            "dimensions": {name: len(dimension) for name, dimension in dataset.dimensions.items()},
            "coordinates": {
                "x": {"size": len(x_values), "min": float(x_values.min()), "max": float(x_values.max()), "step": float(np.median(np.diff(x_values))), "units": getattr(dataset.variables["x"], "units", None)},
                "y": {"size": len(y_values), "min": float(y_values.min()), "max": float(y_values.max()), "step": float(np.median(np.diff(y_values))), "units": getattr(dataset.variables["y"], "units", None)},
                "latitude": {"shape": list(latitude.shape), "min": float(np.nanmin(latitude)), "max": float(np.nanmax(latitude))},
                "longitude": {"shape": list(longitude.shape), "min": float(np.nanmin(longitude)), "max": float(np.nanmax(longitude))},
            },
            "time": {"first": times[0].isoformat(), "last": times[-1].isoformat(), "count": len(times), "interval_seconds": (times[1] - times[0]).total_seconds(), "units": time_variable.units, "calendar": getattr(time_variable, "calendar", "standard")},
            "variables": {name: {"dimensions": list(dataset.variables[name].dimensions), "dtype": str(dataset.variables[name].dtype), **_attributes(dataset.variables[name])} for name in ("vxo", "vyo")},
            "crs": {
                "grid_mapping_attribute": grid_mapping,
                "grid_mapping_variable_present": bool(grid_mapping and grid_mapping in dataset.variables),
                "official_product_proj4": TOPAZ_PROJ4,
                "project_epsg3413": CRS.from_epsg(3413).to_proj4(),
                "equals_epsg3413": CRS.from_proj4(TOPAZ_PROJ4).equals(CRS.from_epsg(3413)),
            },
            "quality_at_noon": {
                "valid_count": valid_count,
                "invalid_count": total - valid_count,
                "valid_ratio": valid_count / total,
                "vxo": _statistics(vxo),
                "vyo": _statistics(vyo),
                "grid_speed": {**_statistics(speed), "p95": float(np.percentile(speed_values, 95))},
            },
            "samples": samples,
            "global_attributes": {name: dataset.getncattr(name) for name in dataset.ncattrs()},
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=Path)
    args = parser.parse_args(argv)
    print(json.dumps([inspect_current(path) for path in args.files], ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
