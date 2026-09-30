"""Inspect NetCDF structure and data ranges without loading the whole file."""

from __future__ import annotations

import argparse
from functools import reduce
from itertools import product
import json
from operator import mul
from pathlib import Path
import sys
from typing import Any, Iterable

from netCDF4 import Dataset, Variable, num2date
import numpy as np

from core.netcdf import open_netcdf


DATASET_VARIABLE_ALIASES: dict[str, tuple[tuple[str, ...], ...]] = {
    "ice": (("ice_conc", "ice_concentration", "sea_ice_concentration", "sic", "siconc"),),
    "wind": (
        ("u10", "u_wind", "eastward_wind", "wind_u"),
        ("v10", "v_wind", "northward_wind", "wind_v"),
    ),
    "current": (
        ("uo", "u_current", "eastward_sea_water_velocity", "current_u"),
        ("vo", "v_current", "northward_sea_water_velocity", "current_v"),
    ),
    "wave": (("swh", "hs", "significant_wave_height", "sea_surface_wave_significant_height"),),
    "bathymetry": (("elevation", "depth", "bathymetry", "z"),),
}
TEMPORAL_DATASET_TYPES = {"ice", "wind", "current", "wave"}


def _product(values: Iterable[int]) -> int:
    return reduce(mul, values, 1)


def _json_scalar(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, np.ndarray):
        return [_json_scalar(item) for item in value.tolist()]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _window_shape(shape: tuple[int, ...], budget: int) -> tuple[int, ...]:
    """Choose a bounded contiguous window shape for a large variable."""

    if not shape or _product(shape) <= budget:
        return shape
    scale = (budget / _product(shape)) ** (1 / len(shape))
    lengths = [max(1, min(size, int(size * scale))) for size in shape]
    while _product(lengths) > budget:
        index = max(range(len(lengths)), key=lengths.__getitem__)
        lengths[index] = max(1, lengths[index] - 1)
    return tuple(lengths)


def _window_slices(
    shape: tuple[int, ...], lengths: tuple[int, ...], anchor: float
) -> tuple[slice, ...]:
    slices: list[slice] = []
    for size, length in zip(shape, lengths):
        start = int(round((size - length) * anchor))
        slices.append(slice(start, start + length))
    return tuple(slices)


def _chunk_slices(shape: tuple[int, ...], budget: int) -> Iterable[tuple[slice, ...]]:
    """Yield exhaustive, bounded-size slices for exact statistics."""

    lengths = _window_shape(shape, budget)
    starts = [range(0, size, length) for size, length in zip(shape, lengths)]
    for offsets in product(*starts):
        yield tuple(
            slice(start, min(size, start + length))
            for start, size, length in zip(offsets, shape, lengths)
        )


def _finite_min_max(data: Any) -> tuple[float | int | None, float | int | None, int]:
    array = np.ma.asarray(data)
    if array.size == 0 or np.ma.count(array) == 0:
        return None, None, 0
    compressed = array.compressed()
    if np.issubdtype(compressed.dtype, np.floating):
        compressed = compressed[np.isfinite(compressed)]
    if compressed.size == 0:
        return None, None, 0
    minimum = _json_scalar(compressed.min())
    maximum = _json_scalar(compressed.max())
    return minimum, maximum, int(compressed.size)


def calculate_min_max(
    variable: Variable,
    *,
    full_stats: bool = False,
    max_sample_values: int = 1_000_000,
) -> dict[str, Any]:
    """Calculate exact or bounded-sample statistics for one numeric variable."""

    try:
        is_numeric = np.issubdtype(variable.dtype, np.number)
    except TypeError:
        is_numeric = False
    if not is_numeric:
        return {"min": None, "max": None, "statistics": "not_numeric", "sample_count": 0}
    if variable.size == 0:
        return {"min": None, "max": None, "statistics": "empty", "sample_count": 0}

    shape = tuple(int(size) for size in variable.shape)
    if full_stats and shape:
        minimum: float | int | None = None
        maximum: float | int | None = None
        count = 0
        for slices in _chunk_slices(shape, max_sample_values):
            chunk_min, chunk_max, chunk_count = _finite_min_max(variable[slices])
            if chunk_min is not None:
                minimum = chunk_min if minimum is None else min(minimum, chunk_min)
                maximum = chunk_max if maximum is None else max(maximum, chunk_max)
                count += chunk_count
        return {"min": minimum, "max": maximum, "statistics": "full", "sample_count": count}

    if variable.size <= max_sample_values or not shape:
        minimum, maximum, count = _finite_min_max(variable[...])
        return {"min": minimum, "max": maximum, "statistics": "full", "sample_count": count}

    per_window_budget = max(1, max_sample_values // 3)
    lengths = _window_shape(shape, per_window_budget)
    minimum = None
    maximum = None
    count = 0
    seen: set[tuple[tuple[int | None, int | None], ...]] = set()
    for anchor in (0.0, 0.5, 1.0):
        slices = _window_slices(shape, lengths, anchor)
        key = tuple((item.start, item.stop) for item in slices)
        if key in seen:
            continue
        seen.add(key)
        chunk_min, chunk_max, chunk_count = _finite_min_max(variable[slices])
        if chunk_min is not None:
            minimum = chunk_min if minimum is None else min(minimum, chunk_min)
            maximum = chunk_max if maximum is None else max(maximum, chunk_max)
            count += chunk_count
    return {"min": minimum, "max": maximum, "statistics": "sampled", "sample_count": count}


def _coordinate_role(name: str, variable: Variable) -> str | None:
    lowered = name.lower()
    standard_name = str(getattr(variable, "standard_name", "")).lower()
    axis = str(getattr(variable, "axis", "")).upper()
    units = str(getattr(variable, "units", "")).lower()
    if standard_name == "latitude" or lowered in {"lat", "latitude", "nav_lat"}:
        return "latitude"
    if standard_name == "longitude" or lowered in {"lon", "longitude", "nav_lon"}:
        return "longitude"
    if standard_name == "time" or lowered in {"time", "valid_time", "forecast_time"} or axis == "T":
        return "time"
    if standard_name == "projection_y_coordinate" or (axis == "Y" and "degrees_north" not in units):
        return "projection_y"
    if standard_name == "projection_x_coordinate" or (axis == "X" and "degrees_east" not in units):
        return "projection_x"
    if "degrees_north" in units:
        return "latitude"
    if "degrees_east" in units:
        return "longitude"
    return None


def _time_range(variable: Variable) -> dict[str, Any] | None:
    units = getattr(variable, "units", None)
    if not units or variable.size == 0:
        return None
    try:
        raw = np.ma.asarray(variable[...]) if variable.size <= 1_000_000 else np.ma.asarray(
            [variable[0], variable[-1]]
        )
        values = raw.compressed()
        if values.size == 0:
            return None
        calendar = getattr(variable, "calendar", "standard")
        converted = num2date([values.min(), values.max()], units=units, calendar=calendar)
        return {
            "variable": variable.name,
            "start": converted[0].isoformat(),
            "end": converted[1].isoformat(),
            "units": str(units),
            "calendar": str(calendar),
        }
    except (TypeError, ValueError, OverflowError, IndexError) as exc:
        return {"variable": variable.name, "error": str(exc), "units": str(units)}


def _has_alias(variable_names: set[str], aliases: tuple[str, ...]) -> bool:
    lowered = {name.lower() for name in variable_names}
    return any(alias in lowered for alias in aliases)


def evaluate_arctic_suitability(report: dict[str, Any], dataset_type: str | None) -> dict[str, Any]:
    """Apply minimal structural checks for the configured Arctic route region."""

    failures: list[str] = []
    warnings: list[str] = []
    coordinates = report.get("coordinate_ranges", {})
    latitude = coordinates.get("latitude")
    longitude = coordinates.get("longitude")

    if not latitude or latitude.get("max") is None:
        failures.append("No usable latitude coordinate was found")
    elif float(latitude["max"]) < 60:
        failures.append("Latitude coverage does not reach the Arctic route region (60°N)")

    if not longitude or longitude.get("min") is None:
        failures.append("No usable longitude coordinate was found")
    elif float(longitude["max"]) < 0 or float(longitude["min"]) > 180:
        failures.append("Longitude coverage does not intersect the configured 0°..180°E region")

    normalized_type = dataset_type.lower() if dataset_type else None
    if normalized_type in DATASET_VARIABLE_ALIASES:
        variable_names = set(report.get("variables", {}))
        for alias_group in DATASET_VARIABLE_ALIASES[normalized_type]:
            if not _has_alias(variable_names, alias_group):
                failures.append(
                    f"Missing required {normalized_type} variable; expected one of {', '.join(alias_group)}"
                )
        if normalized_type in TEMPORAL_DATASET_TYPES and not report.get("time_range"):
            failures.append(f"{normalized_type} data requires a decodable time coordinate")
    elif normalized_type:
        warnings.append(f"No variable rules are defined for dataset type '{normalized_type}'")
    else:
        warnings.append("Dataset type was not supplied; only spatial coverage was checked")

    return {
        "suitable_for_arctic_navigation": not failures,
        "checked_region": {"south": 60.0, "north": 90.0, "west": 0.0, "east": 180.0},
        "failures": failures,
        "warnings": warnings,
    }


def inspect_nc(
    path: str | Path,
    *,
    dataset_type: str | None = None,
    full_stats: bool = False,
    max_sample_values: int = 1_000_000,
) -> dict[str, Any]:
    """Return a JSON-serializable NetCDF inspection report."""

    nc_path = Path(path).expanduser().resolve()
    if not nc_path.is_file():
        raise FileNotFoundError(f"NetCDF file does not exist: {nc_path}")
    if max_sample_values <= 0:
        raise ValueError("max_sample_values must be positive")

    with open_netcdf(nc_path, mode="r") as dataset:
        dimensions = {
            name: {"size": len(dimension), "unlimited": dimension.isunlimited()}
            for name, dimension in dataset.dimensions.items()
        }
        variables: dict[str, dict[str, Any]] = {}
        coordinate_ranges: dict[str, dict[str, Any]] = {}
        projected_coordinate_ranges: dict[str, dict[str, Any]] = {}
        time_range = None

        for name, variable in dataset.variables.items():
            stats = calculate_min_max(
                variable,
                full_stats=full_stats,
                max_sample_values=max_sample_values,
            )
            variables[name] = {
                "dimensions": list(variable.dimensions),
                "shape": list(variable.shape),
                "dtype": str(variable.dtype),
                "units": _json_scalar(getattr(variable, "units", None)),
                "standard_name": _json_scalar(getattr(variable, "standard_name", None)),
                "long_name": _json_scalar(getattr(variable, "long_name", None)),
                **stats,
            }
            role = _coordinate_role(name, variable)
            if role in {"latitude", "longitude"}:
                coordinate_ranges[role] = {
                    "variable": name,
                    "min": stats["min"],
                    "max": stats["max"],
                    "units": _json_scalar(getattr(variable, "units", None)),
                    "statistics": stats["statistics"],
                }
            elif role in {"projection_x", "projection_y"}:
                projected_coordinate_ranges[role] = {
                    "variable": name,
                    "min": stats["min"],
                    "max": stats["max"],
                    "units": _json_scalar(getattr(variable, "units", None)),
                    "statistics": stats["statistics"],
                }
            elif role == "time" and time_range is None:
                time_range = _time_range(variable)

        global_attributes = {
            name: _json_scalar(dataset.getncattr(name)) for name in dataset.ncattrs()
        }
        report: dict[str, Any] = {
            "file": {
                "path": str(nc_path),
                "name": nc_path.name,
                "size_bytes": nc_path.stat().st_size,
                "format": dataset.data_model,
                "disk_format": dataset.disk_format,
            },
            "global_attributes": global_attributes,
            "dimensions": dimensions,
            "variables": variables,
            "coordinate_ranges": coordinate_ranges,
            "projected_coordinate_ranges": projected_coordinate_ranges,
            "time_range": time_range,
            "statistics_mode": "full" if full_stats else "bounded_sample",
        }
        report["arctic_route_check"] = evaluate_arctic_suitability(report, dataset_type)
        return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="NetCDF file path")
    parser.add_argument(
        "--dataset-type",
        choices=sorted(DATASET_VARIABLE_ALIASES),
        help="Apply type-specific variable checks",
    )
    parser.add_argument(
        "--full-stats",
        action="store_true",
        help="Scan every numeric value (may be slow for multi-GB files)",
    )
    parser.add_argument(
        "--max-sample-values",
        type=int,
        default=1_000_000,
        help="Maximum numeric values sampled per variable by default",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = inspect_nc(
            args.path,
            dataset_type=args.dataset_type,
            full_stats=args.full_stats,
            max_sample_values=args.max_sample_values,
        )
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"NC inspection failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
