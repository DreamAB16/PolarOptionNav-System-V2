"""Download the two time-aligned Copernicus Marine Arctic wave days."""

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


PRODUCT_ID = "ARCTIC_ANALYSIS_FORECAST_WAV_002_014"
DATASET_ID = "dataset-wam-arctic-1hr3km-be"
DATASET_VERSION = "202411"
VARIABLES = ("VHM0", "VTPK", "VMDR")
PRESET_DATES = (date(2025, 2, 15), date(2025, 8, 15))
DEFAULT_OUTPUT_DIRECTORY = get_dataset_path("wave") / "raw"
LOGGER = logging.getLogger("polaroptionnav.data_tools.download_copernicus_wave")


def resolve_output_directory(data_root: Path | None, output_directory: Path | None) -> Path:
    if output_directory is not None:
        return output_directory
    return data_root / "environment" / "wave" / "raw" if data_root else DEFAULT_OUTPUT_DIRECTORY


@dataclass(frozen=True)
class WaveDownloadResult:
    date: date
    path: Path
    status: str


def parse_date(value: str) -> date:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD format") from error
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
    return output_directory / f"Copernicus_wave_{target_date:%Y%m%d}.nc"


def _find_partial(destination: Path) -> Path | None:
    """Find the exact or Toolbox-suffixed partial response for a target."""

    candidates = [destination.with_name(f"{destination.stem}.part.nc")]
    candidates.extend(sorted(destination.parent.glob(f"{destination.stem}.part.nc.*"), key=lambda p: p.stat().st_mtime, reverse=True))
    return next((path for path in candidates if path.is_file() and path.stat().st_size > 0), None)


def credentials_available() -> bool:
    """Check only standard Toolbox credential locations; never read their content."""

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


def inspect_wave_file(path: Path, expected_date: date) -> dict[str, object]:
    """Validate a completed partial before publishing it as raw data."""

    with open_netcdf(path) as dataset:
        missing = set(VARIABLES).difference(dataset.variables)
        if missing:
            raise ValueError(f"Downloaded wave file is missing: {', '.join(sorted(missing))}")
        if "time" not in dataset.variables:
            raise ValueError("Downloaded wave file has no time coordinate.")
        time_variable = dataset.variables["time"]
        values = list(num2date(
            time_variable[:],
            units=time_variable.units,
            calendar=getattr(time_variable, "calendar", "standard"),
            only_use_cftime_datetimes=False,
        ))
        times = [
            value.replace(tzinfo=timezone.utc)
            if value.tzinfo is None
            else value.astimezone(timezone.utc)
            for value in values
        ]
        if len(times) != 24:
            raise ValueError(f"Expected 24 hourly wave fields, found {len(times)}.")
        if (
            times[0].date() != expected_date
            or times[0].hour != 0
            or times[-1].date() != expected_date
            or times[-1].hour != 23
        ):
            raise ValueError(f"Unexpected wave time coverage: {times[0]} .. {times[-1]}")
        return {
            "time_count": len(times),
            "first_time": times[0].isoformat(),
            "last_time": times[-1].isoformat(),
            "dimensions": {name: len(value) for name, value in dataset.dimensions.items()},
        }


def _load_subset() -> Callable[..., object]:
    try:
        import copernicusmarine
    except ImportError as error:
        raise RuntimeError("Install tools/data_tools/requirements.txt first.") from error
    return copernicusmarine.subset


def download_day(
    target_date: date,
    *,
    output_directory: Path = DEFAULT_OUTPUT_DIRECTORY,
    retries: int = 2,
    force: bool = False,
    subset_function: Callable[..., object] | None = None,
) -> WaveDownloadResult:
    """Download, validate and atomically publish one UTC day."""

    if target_date.year != 2025 or target_date.month not in (2, 8):
        raise ValueError("Only February or August 2025 are supported.")
    if retries < 0:
        raise ValueError("retries must not be negative")
    destination = output_path(target_date, output_directory)
    partial = destination.with_name(f"{destination.stem}.part.nc")
    if destination.is_file() and not force:
        inspect_wave_file(destination, target_date)
        return WaveDownloadResult(target_date, destination, "skipped")

    output_directory.mkdir(parents=True, exist_ok=True)
    if partial.is_file() and not force:
        try:
            inspect_wave_file(partial, target_date)
            partial.replace(destination)
            return WaveDownloadResult(target_date, destination, "recovered")
        except (OSError, ValueError):
            # An incomplete NetCDF cannot be resumed safely at the file level;
            # the Toolbox restarts its chunked request into the same .part target.
            partial.unlink(missing_ok=True)
    elif force:
        partial.unlink(missing_ok=True)

    start = datetime.combine(target_date, time(0), tzinfo=timezone.utc)
    end = datetime.combine(target_date, time(23), tzinfo=timezone.utc)
    subset = subset_function or _load_subset()
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            LOGGER.info("下载海浪 %s（第 %d/%d 次）", target_date, attempt + 1, retries + 1)
            subset(
                dataset_id=DATASET_ID,
                dataset_version=DATASET_VERSION,
                variables=list(VARIABLES),
                minimum_longitude=-180.0,
                maximum_longitude=180.0,
                minimum_latitude=30.0,
                maximum_latitude=90.0,
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
            inspect_wave_file(candidate, target_date)
            if candidate != partial:
                candidate.replace(partial)
            os.replace(partial, destination)
            return WaveDownloadResult(target_date, destination, "downloaded")
        except Exception as error:
            last_error = error
            if attempt < retries:
                delay = 2**attempt
                LOGGER.warning("海浪下载失败，%d秒后重试：%s", delay, error)
                time_module.sleep(delay)
    # Preserve a partial artifact after terminal failure for diagnosis/recovery.
    raise RuntimeError(f"Copernicus wave download failed; partial kept at {partial}: {last_error}") from last_error


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
                print(
                    f"{PRODUCT_ID} | {DATASET_ID} version={DATASET_VERSION} | "
                    f"{target_date} 00:00..23:00 UTC | VHM0,VTPK,VMDR | "
                    f"lat=30..90 lon=-180..180 | {output_path(target_date, output_directory)}"
                )
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
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Copernicus 海浪下载失败：{error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
