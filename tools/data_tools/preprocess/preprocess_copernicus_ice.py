"""Validate and compress a Copernicus neXtSIM sea-ice NetCDF scene."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import hashlib
from pathlib import Path
import re
import sys
from typing import Any

import numpy as np
from netCDF4 import num2date

from core.config.environment_config import get_dataset_path
from core.netcdf import open_netcdf


REQUIRED_STANDARD_NAMES = {
    "sea_ice_area_fraction",
    "sea_ice_thickness",
    "sea_ice_classification",
    "eastward_sea_ice_velocity",
    "northward_sea_ice_velocity",
    "surface_snow_thickness",
}
FILENAME_PATTERN = re.compile(r"arctic_ice_(\d{8})\.nc$", re.IGNORECASE)
DEFAULT_OUTPUT_DIRECTORY = get_dataset_path("ice") / "processed" / "copernicus"
COPY_ROWS = 64


@dataclass(frozen=True)
class PreprocessResult:
    input: Path
    output: Path
    input_size_bytes: int
    output_size_bytes: int
    time_range: tuple[str, str]
    spatial_range: dict[str, tuple[float, float]]
    grid_size: dict[str, int]
    variables: tuple[str, ...]


@dataclass(frozen=True)
class PreprocessValidation:
    """Lightweight raw/processed equivalence check for one daily scene."""

    input: Path
    output: Path
    date: str
    variables: tuple[str, ...]
    samples_per_variable: int
    fill_values_preserved: bool


def default_output_path(input_path: Path, output_directory: Path = DEFAULT_OUTPUT_DIRECTORY) -> Path:
    match = FILENAME_PATTERN.fullmatch(input_path.name)
    if not match:
        raise ValueError("Copernicus input filename must use arctic_ice_YYYYMMDD.nc")
    return output_directory / input_path.name


def _copy_attributes(source: Any, target: Any, *, excluded: set[str] | None = None) -> None:
    excluded = excluded or set()
    target.setncatts({name: source.getncattr(name) for name in source.ncattrs() if name not in excluded})


def _discover_variables(dataset: Any) -> tuple[str, ...]:
    by_standard_name: dict[str, list[str]] = {}
    for name, variable in dataset.variables.items():
        standard_name = getattr(variable, "standard_name", None)
        if standard_name:
            by_standard_name.setdefault(str(standard_name), []).append(name)
    missing = REQUIRED_STANDARD_NAMES.difference(by_standard_name)
    if missing:
        raise ValueError(f"Copernicus input is missing CF variables: {', '.join(sorted(missing))}")
    classifications = by_standard_name["sea_ice_classification"]
    if len(classifications) < 2:
        raise ValueError("Copernicus input must provide young-ice and multi-year-ice fractions.")
    selected = [
        by_standard_name["sea_ice_area_fraction"][0],
        by_standard_name["sea_ice_thickness"][0],
        *classifications,
        by_standard_name["eastward_sea_ice_velocity"][0],
        by_standard_name["northward_sea_ice_velocity"][0],
        by_standard_name["surface_snow_thickness"][0],
    ]
    return tuple(dict.fromkeys(selected))


def _validate_coordinates(dataset: Any) -> tuple[str, str, str]:
    roles: dict[str, str] = {}
    for name, variable in dataset.variables.items():
        standard_name = getattr(variable, "standard_name", None)
        if standard_name in {"time", "latitude", "longitude"}:
            roles[str(standard_name)] = name
        units = str(getattr(variable, "units", "")).lower()
        if name.lower() in {"lat", "latitude"} or "degrees_north" in units:
            roles["latitude"] = name
        if name.lower() in {"lon", "longitude"} or "degrees_east" in units:
            roles["longitude"] = name
        if name.lower() in {"time", "valid_time", "forecast_time"} or getattr(variable, "axis", None) == "T":
            roles["time"] = name
    missing = {"time", "latitude", "longitude"}.difference(roles)
    if missing:
        raise ValueError(f"Copernicus input is missing coordinates: {', '.join(sorted(missing))}")
    time_name, latitude_name, longitude_name = roles["time"], roles["latitude"], roles["longitude"]
    if dataset.variables[latitude_name].ndim != 1 or dataset.variables[longitude_name].ndim != 1:
        raise ValueError("Copernicus processed flow requires one-dimensional latitude/longitude coordinates.")
    return time_name, latitude_name, longitude_name


def preprocess_copernicus_ice(
    input_path: str | Path,
    output_path: str | Path | None = None,
    *,
    compression_level: int = 4,
) -> PreprocessResult:
    """Copy required fields to a compressed CF NetCDF without changing values."""

    source_path = Path(input_path).resolve()
    if not source_path.is_file():
        raise FileNotFoundError(f"Copernicus input does not exist: {source_path}")
    if not 1 <= compression_level <= 9:
        raise ValueError("compression_level must be between 1 and 9")
    destination = (
        Path(output_path).resolve()
        if output_path is not None
        else default_output_path(source_path).resolve()
    )
    if destination == source_path:
        raise ValueError("output_path must differ from input_path")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp.nc")
    if temporary.exists():
        temporary.unlink()

    try:
        with open_netcdf(source_path, "r") as source:
            time_name, latitude_name, longitude_name = _validate_coordinates(source)
            data_names = _discover_variables(source)
            coordinate_names = (time_name, latitude_name, longitude_name)
            with open_netcdf(temporary, "w", format="NETCDF4") as target:
                _copy_attributes(source, target)
                target.setncattr("processing_level", "compressed_cf_copy")
                target.setncattr("processing_history", f"Compressed by PolarOptionNav data tools at {datetime.now().isoformat()}")
                for name, dimension in source.dimensions.items():
                    target.createDimension(name, None if dimension.isunlimited() else len(dimension))

                for name in (*coordinate_names, *data_names):
                    source_variable = source.variables[name]
                    fill_value = getattr(source_variable, "_FillValue", None)
                    kwargs: dict[str, Any] = {}
                    if fill_value is not None:
                        kwargs["fill_value"] = fill_value
                    if source_variable.ndim >= 2:
                        kwargs.update(zlib=True, complevel=compression_level, shuffle=True)
                        if source_variable.ndim == 3:
                            kwargs["chunksizes"] = (
                                1,
                                min(COPY_ROWS, source_variable.shape[1]),
                                min(1024, source_variable.shape[2]),
                            )
                    target_dtype = (
                        np.dtype("float32")
                        if name in data_names and np.issubdtype(source_variable.dtype, np.floating)
                        else source_variable.dtype
                    )
                    target_variable = target.createVariable(
                        name,
                        target_dtype,
                        source_variable.dimensions,
                        **kwargs,
                    )
                    _copy_attributes(source_variable, target_variable, excluded={"_FillValue"})
                    if source_variable.ndim != 3:
                        target_variable[:] = source_variable[:]
                        continue
                    for time_index in range(source_variable.shape[0]):
                        for row_start in range(0, source_variable.shape[1], COPY_ROWS):
                            row_stop = min(source_variable.shape[1], row_start + COPY_ROWS)
                            target_variable[time_index, row_start:row_stop, :] = source_variable[
                                time_index, row_start:row_stop, :
                            ]
        temporary.replace(destination)
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise

    with open_netcdf(destination, "r") as processed:
        latitude = np.ma.asarray(processed.variables[latitude_name][:]).compressed()
        longitude = np.ma.asarray(processed.variables[longitude_name][:]).compressed()
        time_variable = processed.variables[time_name]
        time_values = np.ma.asarray(time_variable[:]).compressed()
        decoded = num2date(
            [time_values.min(), time_values.max()],
            units=time_variable.units,
            calendar=getattr(time_variable, "calendar", "standard"),
        )
    return PreprocessResult(
        input=source_path,
        output=destination,
        input_size_bytes=source_path.stat().st_size,
        output_size_bytes=destination.stat().st_size,
        time_range=(decoded[0].isoformat(), decoded[1].isoformat()),
        spatial_range={
            "latitude": (float(latitude.min()), float(latitude.max())),
            "longitude": (float(longitude.min()), float(longitude.max())),
        },
        grid_size={"latitude": latitude.size, "longitude": longitude.size},
        variables=data_names,
    )


def validate_processed_copernicus_ice(
    input_path: str | Path,
    output_path: str | Path,
    *,
    samples_per_variable: int = 3,
) -> PreprocessValidation:
    """Verify a compressed scene without loading the full Arctic grid.

    Coordinates, CF-selected variables, shapes, dtypes and ``_FillValue`` are
    checked exactly.  A deterministic selection of values per variable catches
    accidental conversion or reordering while keeping validation inexpensive.
    """

    source_path = Path(input_path).resolve()
    destination = Path(output_path).resolve()
    if not source_path.is_file() or not destination.is_file():
        raise FileNotFoundError("Both input and processed Copernicus files must exist.")
    if samples_per_variable < 1:
        raise ValueError("samples_per_variable must be positive")
    match = FILENAME_PATTERN.fullmatch(destination.name)
    if match is None:
        raise ValueError("Processed filename must use arctic_ice_YYYYMMDD.nc")
    expected_date = match.group(1)

    with open_netcdf(source_path, "r") as source, open_netcdf(destination, "r") as processed:
        time_name, latitude_name, longitude_name = _validate_coordinates(source)
        processed_time, processed_latitude, processed_longitude = _validate_coordinates(processed)
        if (time_name, latitude_name, longitude_name) != (processed_time, processed_latitude, processed_longitude):
            raise ValueError("Processed coordinate names differ from raw source.")
        variables = _discover_variables(source)
        if _discover_variables(processed) != variables:
            raise ValueError("Processed CF variable selection differs from raw source.")
        for coordinate in (time_name, latitude_name, longitude_name):
            raw = source.variables[coordinate]
            copied = processed.variables[coordinate]
            if raw.shape != copied.shape or raw.dtype != copied.dtype:
                raise ValueError(f"Processed coordinate {coordinate} shape or dtype differs from raw source.")
            if not np.array_equal(np.asarray(raw[:]), np.asarray(copied[:]), equal_nan=True):
                raise ValueError(f"Processed coordinate {coordinate} values differ from raw source.")

        time_variable = processed.variables[time_name]
        time_value = np.ma.asarray(time_variable[:]).compressed()
        if not time_value.size:
            raise ValueError("Processed file has no decodable time values.")
        decoded = num2date(
            time_value[0],
            units=time_variable.units,
            calendar=getattr(time_variable, "calendar", "standard"),
        )
        if decoded.strftime("%Y%m%d") != expected_date:
            raise ValueError("Processed filename date does not match its time coordinate.")

        seed = int(hashlib.sha256(expected_date.encode("ascii")).hexdigest()[:16], 16)
        generator = np.random.default_rng(seed)
        fill_values_preserved = True
        for name in variables:
            raw = source.variables[name]
            copied = processed.variables[name]
            expected_dtype = (
                np.dtype("float32") if np.issubdtype(raw.dtype, np.floating) else raw.dtype
            )
            if raw.shape != copied.shape or copied.dtype != expected_dtype:
                raise ValueError(f"Processed variable {name} shape or dtype differs from the processed contract.")
            raw_fill = getattr(raw, "_FillValue", None)
            copied_fill = getattr(copied, "_FillValue", None)
            fills_equal = (
                raw_fill == copied_fill
                or (
                    raw_fill is not None
                    and copied_fill is not None
                    and np.isnan(raw_fill)
                    and np.isnan(copied_fill)
                )
            )
            if not fills_equal:
                fill_values_preserved = False
                raise ValueError(f"Processed variable {name} _FillValue differs from raw source.")
            for _ in range(samples_per_variable):
                index = tuple(int(generator.integers(size)) for size in raw.shape)
                raw_value = np.ma.asarray(raw[index])
                copied_value = np.ma.asarray(copied[index])
                if np.ma.is_masked(raw_value) != np.ma.is_masked(copied_value):
                    raise ValueError(f"Processed variable {name} mask differs from raw source at {index}.")
                if not np.ma.is_masked(raw_value) and not np.isclose(
                    float(raw_value), float(copied_value), rtol=1e-6, atol=1e-7, equal_nan=True
                ):
                    raise ValueError(f"Processed variable {name} value differs from raw source at {index}.")

    return PreprocessValidation(
        input=source_path,
        output=destination,
        date=expected_date,
        variables=variables,
        samples_per_variable=samples_per_variable,
        fill_values_preserved=fill_values_preserved,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--compression-level", type=int, default=4)
    return parser


def _configure_console_encoding() -> None:
    """Keep Chinese status messages readable on Windows terminals."""

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    _configure_console_encoding()
    args = build_parser().parse_args(argv)
    try:
        result = preprocess_copernicus_ice(args.input, args.output, compression_level=args.compression_level)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Copernicus 海冰预处理失败：{exc}", file=sys.stderr)
        return 1
    print(f"输入：{result.input}")
    print(f"输出：{result.output}")
    print(f"大小：{result.input_size_bytes} → {result.output_size_bytes} bytes")
    print(f"时间：{result.time_range[0]} → {result.time_range[1]}")
    print(f"空间范围：{result.spatial_range}")
    print(f"网格：{result.grid_size}")
    print(f"变量：{', '.join(result.variables)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
