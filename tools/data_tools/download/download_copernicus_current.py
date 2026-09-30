"""Download two time-aligned TOPAZ5 detided surface-current days."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import logging
import os
from pathlib import Path
import sys
import time as time_module
from typing import Callable

from netCDF4 import num2date

from core.config.environment_config import get_dataset_path
from core.netcdf import open_netcdf


PRODUCT_ID = "ARCTIC_ANALYSISFORECAST_PHY_002_001"
DATASET_ID = "cmems_mod_arc_phy_anfc_6km_detided_PT1H-i"
DATASET_PART = "originalGrid"
VARIABLES = ("vxo", "vyo")
PRESET_DATES = (date(2025, 2, 15), date(2025, 8, 15))
DEFAULT_OUTPUT_DIRECTORY = get_dataset_path("current") / "raw"
LOGGER = logging.getLogger("polaroptionnav.data_tools.download_copernicus_current")


def resolve_output_directory(data_root: Path | None, output_directory: Path | None) -> Path:
    if output_directory is not None:
        return output_directory
    return data_root / "environment" / "current" / "raw" if data_root else DEFAULT_OUTPUT_DIRECTORY


@dataclass(frozen=True)
class CurrentDownloadResult:
    date: date
    path: Path
    status: str


def parse_date(value: str) -> date:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD format") from exc
    if parsed.year != 2025 or parsed.month not in (2, 8):
        raise argparse.ArgumentTypeError("date must fall in February or August 2025")
    return parsed


def build_dates(single_date: date | None, start: date | None, end: date | None) -> list[date]:
    """Build an inclusive same-month sequence for the two experiment seasons."""

    if single_date is not None:
        if start is not None or end is not None:
            raise ValueError("Use --date or --start/--end, not both.")
        return [single_date]
    if start is None or end is None:
        raise ValueError("Provide --date or both --start and --end.")
    if start > end or start.year != end.year or start.month != end.month:
        raise ValueError("--start/--end must be an ascending range in one month.")
    if start.year != 2025 or start.month not in (2, 8):
        raise ValueError("Only February or August 2025 are supported.")
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def output_path(target_date: date, output_directory: Path = DEFAULT_OUTPUT_DIRECTORY) -> Path:
    return output_directory / f"Copernicus_current_{target_date:%Y%m%d}.nc"


def _find_partial(destination: Path) -> Path | None:
    """Find the exact or Toolbox-suffixed partial response for a target."""

    candidates = [destination.with_name(f"{destination.stem}.part.nc")]
    candidates.extend(sorted(destination.parent.glob(f"{destination.stem}.part.nc.*"), key=lambda p: p.stat().st_mtime, reverse=True))
    return next((path for path in candidates if path.is_file() and path.stat().st_size > 0), None)


def credentials_available() -> bool:
    environment_credentials = bool(
        os.getenv("COPERNICUSMARINE_SERVICE_USERNAME")
        and os.getenv("COPERNICUSMARINE_SERVICE_PASSWORD")
    )
    home = Path.home()
    return environment_credentials or any(
        path.is_file()
        for path in (
            home / ".copernicusmarine" / ".copernicusmarine-credentials",
            home / ".netrc",
            home / "_netrc",
        )
    )


def inspect_current_file(path: Path, expected_date: date) -> dict[str, object]:
    """Perform the minimum strict checks before a partial file becomes official raw data."""
    with open_netcdf(path) as dataset:
        for name, standard_name in (
            ("vxo", "sea_water_x_velocity"),
            ("vyo", "sea_water_y_velocity"),
        ):
            if name not in dataset.variables:
                raise ValueError(f"Downloaded current file is missing {name}.")
            variable = dataset.variables[name]
            if getattr(variable, "standard_name", None) != standard_name:
                raise ValueError(f"{name} has unexpected standard_name.")
            if getattr(variable, "units", None) != "m s-1":
                raise ValueError(f"{name} has unexpected units.")
            if variable.dimensions != ("time", "y", "x"):
                raise ValueError(f"{name} is not an hourly surface y/x field.")
        if not {"time", "x", "y", "latitude", "longitude"}.issubset(dataset.variables):
            raise ValueError("Downloaded current file is missing required coordinates.")
        time_variable = dataset.variables["time"]
        values = num2date(
            time_variable[:],
            units=time_variable.units,
            calendar=getattr(time_variable, "calendar", "standard"),
            only_use_cftime_datetimes=False,
        )
        if len(values) != 24:
            raise ValueError(f"Expected 24 hourly current fields, found {len(values)}.")
        first = values[0].replace(tzinfo=timezone.utc) if values[0].tzinfo is None else values[0].astimezone(timezone.utc)
        last = values[-1].replace(tzinfo=timezone.utc) if values[-1].tzinfo is None else values[-1].astimezone(timezone.utc)
        if first.date() != expected_date or first.hour != 0 or last.date() != expected_date or last.hour != 23:
            raise ValueError(f"Unexpected current time coverage: {first} .. {last}")
        return {
            "time_count": len(values),
            "first_time": first.isoformat(),
            "last_time": last.isoformat(),
            "x_count": len(dataset.dimensions["x"]),
            "y_count": len(dataset.dimensions["y"]),
        }


def _load_subset() -> Callable[..., object]:
    try:
        import copernicusmarine
    except ImportError as exc:
        raise RuntimeError("Install tools/data_tools/requirements.txt first.") from exc
    return copernicusmarine.subset


def download_day(
    target_date: date,
    *,
    output_directory: Path = DEFAULT_OUTPUT_DIRECTORY,
    retries: int = 2,
    force: bool = False,
    subset_function: Callable[..., object] | None = None,
) -> CurrentDownloadResult:
    if target_date.year != 2025 or target_date.month not in (2, 8):
        raise ValueError("Only February or August 2025 are supported.")
    if retries < 0:
        raise ValueError("retries must not be negative")
    destination = output_path(target_date, output_directory)
    # Toolbox appends .nc when the explicit filename has another suffix.
    # Keep both the partial marker and a final .nc suffix so our validation
    # and atomic rename address the exact file it creates.
    partial = destination.with_name(f"{destination.stem}.part.nc")
    if destination.is_file() and not force:
        inspect_current_file(destination, target_date)
        return CurrentDownloadResult(target_date, destination, "skipped")
    output_directory.mkdir(parents=True, exist_ok=True)
    if partial.is_file() and not force:
        try:
            inspect_current_file(partial, target_date)
            partial.replace(destination)
            return CurrentDownloadResult(target_date, destination, "recovered")
        except (OSError, ValueError):
            partial.unlink(missing_ok=True)
    else:
        partial.unlink(missing_ok=True)
    start = datetime.combine(target_date, time(0), tzinfo=timezone.utc)
    end = datetime.combine(target_date, time(23), tzinfo=timezone.utc)
    subset = subset_function or _load_subset()
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            LOGGER.info("下载海流 %s（第 %d/%d 次）", target_date, attempt + 1, retries + 1)
            subset(
                dataset_id=DATASET_ID,
                dataset_part=DATASET_PART,
                variables=list(VARIABLES),
                start_datetime=start,
                end_datetime=end,
                output_directory=output_directory,
                output_filename=partial.name,
                file_format="netcdf",
                overwrite=True,
                disable_progress_bar=False,
                netcdf_compression_level=4,
            )
            candidate = _find_partial(destination)
            if candidate is None:
                raise RuntimeError(f"Copernicus Marine did not create {partial}")
            inspect_current_file(candidate, target_date)
            if candidate != partial:
                candidate.replace(partial)
            if destination.exists():
                destination.unlink()
            partial.replace(destination)
            return CurrentDownloadResult(target_date, destination, "downloaded")
        except Exception as exc:
            last_error = exc
            if attempt < retries:
                delay = 2**attempt
                LOGGER.warning("海流下载失败，%d秒后重试：%s", delay, exc)
                time_module.sleep(delay)
    partial.unlink(missing_ok=True)
    raise RuntimeError(f"Copernicus current download failed: {last_error}") from last_error


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--date", type=parse_date)
    group.add_argument("--start", type=parse_date)
    group.add_argument("--all", action="store_true")
    parser.add_argument("--end", type=parse_date, help="inclusive end date; required with --start")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--data-root", type=Path, help="PolarData root; overrides configured default output")
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        dates = list(PRESET_DATES) if args.all else build_dates(args.date, args.start, args.end)
        output_directory = resolve_output_directory(args.data_root, args.output_dir)
        if args.dry_run:
            for target_date in dates:
                print(f"{PRODUCT_ID} | {DATASET_ID} | part={DATASET_PART} | {target_date} 00:00..23:00 UTC | vxo,vyo | {output_path(target_date, output_directory)}")
            return 0
        if not credentials_available():
            raise RuntimeError("未找到本机 Copernicus Marine 登录凭据，请先运行 copernicusmarine login。")
        for target_date in dates:
            result = download_day(
                target_date,
                output_directory=output_directory,
                retries=args.retries,
                force=args.force,
            )
            print(f"{result.status}: {result.path}")
        return 0
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Copernicus 海流下载失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
