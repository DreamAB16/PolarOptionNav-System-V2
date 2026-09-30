"""Download Copernicus Marine neXtSIM hourly Arctic sea-ice subsets.

Credentials are deliberately delegated to the Copernicus Marine Toolbox. Set
``COPERNICUSMARINE_SERVICE_USERNAME`` and
``COPERNICUSMARINE_SERVICE_PASSWORD`` or run ``copernicusmarine login`` once;
secrets are never accepted as command-line arguments or stored in this project.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import logging
import os
from pathlib import Path
import sys
import time as time_module
from typing import Callable, Iterable

from core.config.environment_config import get_dataset_path
from tools.data_tools.inspect.inspect_nc import inspect_nc


PRODUCT_ID = "ARCTIC_ANALYSISFORECAST_PHY_ICE_002_011"
DATASET_ID = "cmems_mod_arc_phy_anfc_nextsim_hm"
VARIABLES = ("siconc", "sithick", "siconc_my", "siconc_young", "vxsi", "vysi", "sisnthick")
REQUIRED_STANDARD_NAMES = {
    "sea_ice_area_fraction",
    "sea_ice_thickness",
    "sea_ice_classification",
    "surface_snow_thickness",
}
DRIFT_STANDARD_NAME_GROUPS = (
    {"eastward_sea_ice_velocity", "sea_ice_x_velocity"},
    {"northward_sea_ice_velocity", "sea_ice_y_velocity"},
)
DEFAULT_OUTPUT_DIRECTORY = get_dataset_path("ice") / "raw" / "copernicus"
LOGGER = logging.getLogger("polaroptionnav.data_tools.download_copernicus_ice")


def resolve_output_directory(data_root: Path | None, output_directory: Path | None) -> Path:
    if output_directory is not None:
        return output_directory
    return data_root / "environment" / "ice" / "raw" / "copernicus" if data_root else DEFAULT_OUTPUT_DIRECTORY


@dataclass(frozen=True)
class CopernicusDownloadResult:
    """One requested daily scene and its validation result."""

    date: date
    path: Path
    status: str
    variable_map: dict[str, str]


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD format") from exc


def build_dates(single_date: date | None, start: date | None, end: date | None) -> list[date]:
    """Validate CLI date modes and return an inclusive daily sequence."""

    if single_date is not None:
        if start is not None or end is not None:
            raise ValueError("Use --date or --start/--end, not both.")
        return [single_date]
    if start is None or end is None:
        raise ValueError("Provide --date or both --start and --end.")
    if start > end:
        raise ValueError("--start must not be later than --end.")
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def output_path(target_date: date, output_directory: Path = DEFAULT_OUTPUT_DIRECTORY) -> Path:
    return output_directory / f"arctic_ice_{target_date:%Y%m%d}.nc"


def _find_partial(destination: Path) -> Path | None:
    """Find the explicit .part file or the Toolbox's temporary-suffixed file."""

    candidates = [destination.with_name(f"{destination.stem}.part.nc")]
    candidates.extend(sorted(destination.parent.glob(f"{destination.stem}.part.nc.*"), key=lambda p: p.stat().st_mtime, reverse=True))
    return next((path for path in candidates if path.is_file() and path.stat().st_size > 0), None)


def requested_instant(target_date: date, hour: int = 12) -> datetime:
    if not 0 <= hour <= 23:
        raise ValueError("hour must be between 0 and 23")
    return datetime.combine(target_date, time(hour=hour), tzinfo=timezone.utc)


def credentials_available() -> bool:
    """Return whether the Toolbox can authenticate without an interactive prompt."""

    environment_credentials = bool(
        os.getenv("COPERNICUSMARINE_SERVICE_USERNAME")
        and os.getenv("COPERNICUSMARINE_SERVICE_PASSWORD")
    )
    home = Path.home()
    credential_files = (
        home / ".copernicusmarine" / ".copernicusmarine-credentials",
        home / ".netrc",
        home / "_netrc",
    )
    return environment_credentials or any(path.is_file() for path in credential_files)


def _variable_map(report: dict[str, object]) -> dict[str, str]:
    variables = report.get("variables")
    if not isinstance(variables, dict):
        raise ValueError("NetCDF inspection did not return variables.")
    by_standard_name: dict[str, list[str]] = {}
    for name, metadata in variables.items():
        if isinstance(metadata, dict) and metadata.get("standard_name"):
            by_standard_name.setdefault(str(metadata["standard_name"]), []).append(str(name))

    missing = sorted(REQUIRED_STANDARD_NAMES.difference(by_standard_name))
    for alternatives in DRIFT_STANDARD_NAME_GROUPS:
        if not alternatives.intersection(by_standard_name):
            missing.append(" or ".join(sorted(alternatives)))
    if missing:
        raise ValueError(f"Copernicus sea-ice file is missing required metadata: {', '.join(missing)}")

    mapping = {
        "concentration": by_standard_name["sea_ice_area_fraction"][0],
        "thickness": by_standard_name["sea_ice_thickness"][0],
        "snow_thickness": by_standard_name["surface_snow_thickness"][0],
    }
    classifications = by_standard_name["sea_ice_classification"]
    mapping["ice_type_multi_year"] = next(
        (name for name in classifications if "multi" in str(variables[name].get("long_name", "")).lower()),
        classifications[0],
    )
    mapping["ice_type_young"] = next(
        (name for name in classifications if "young" in str(variables[name].get("long_name", "")).lower()),
        classifications[-1],
    )
    for key, alternatives in zip(("drift_u", "drift_v"), DRIFT_STANDARD_NAME_GROUPS):
        standard_name = next(name for name in alternatives if name in by_standard_name)
        mapping[key] = by_standard_name[standard_name][0]
    return mapping


def inspect_download(path: Path) -> dict[str, str]:
    """Inspect the downloaded NC and derive a semantic mapping from CF metadata."""

    return _variable_map(inspect_nc(path, dataset_type="ice"))


def _load_toolbox_subset() -> Callable[..., object]:
    try:
        import copernicusmarine
    except ImportError as exc:
        raise RuntimeError(
            "copernicusmarine is required; install tools/data_tools/requirements.txt"
        ) from exc
    return copernicusmarine.subset


def download_scene(
    target_date: date,
    *,
    output_directory: Path = DEFAULT_OUTPUT_DIRECTORY,
    hour: int = 12,
    south: float = 60.0,
    north: float = 90.0,
    west: float = -180.0,
    east: float = 180.0,
    retries: int = 2,
    credentials_file: Path | None = None,
    subset_function: Callable[..., object] | None = None,
) -> CopernicusDownloadResult:
    """Download and validate one instant without exposing credentials."""

    if not -90 <= south < north <= 90:
        raise ValueError("latitude bounds must satisfy -90 <= south < north <= 90")
    if not -180 <= west < east <= 180:
        raise ValueError("longitude bounds must satisfy -180 <= west < east <= 180")
    if retries < 0:
        raise ValueError("retries must not be negative")

    destination = output_path(target_date, output_directory)
    if destination.is_file():
        mapping = inspect_download(destination)
        return CopernicusDownloadResult(target_date, destination, "skipped", mapping)

    output_directory.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(f"{destination.stem}.part.nc")
    if partial.is_file():
        try:
            mapping = inspect_download(partial)
            partial.replace(destination)
            return CopernicusDownloadResult(target_date, destination, "recovered", mapping)
        except (OSError, ValueError):
            # The Toolbox cannot resume a truncated NetCDF container.  Restart
            # its server-side request into the same explicit .part target.
            partial.unlink(missing_ok=True)
    subset = subset_function or _load_toolbox_subset()
    instant = requested_instant(target_date, hour)
    kwargs = {
        "dataset_id": DATASET_ID,
        "variables": list(VARIABLES),
        "minimum_longitude": west,
        "maximum_longitude": east,
        "minimum_latitude": south,
        "maximum_latitude": north,
        "start_datetime": instant,
        "end_datetime": instant,
        "output_directory": output_directory,
        "output_filename": partial.name,
        "file_format": "netcdf",
        "overwrite": True,
        "skip_existing": False,
        "netcdf_compression_level": 4,
    }
    if credentials_file is not None:
        kwargs["credentials_file"] = credentials_file

    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            LOGGER.info("下载 Copernicus 海冰 %s（第 %d/%d 次）", instant.isoformat(), attempt + 1, retries + 1)
            subset(**kwargs)
            candidate = _find_partial(destination)
            if candidate is None:
                raise RuntimeError(f"Copernicus Marine did not create {partial}")
            mapping = inspect_download(candidate)
            os.replace(candidate, destination)
            LOGGER.info("下载并验证完成：%s", destination)
            return CopernicusDownloadResult(target_date, destination, "downloaded", mapping)
        except Exception as exc:  # Toolbox raises several transport-specific exception types.
            last_error = exc
            if attempt < retries:
                delay = 2**attempt
                LOGGER.warning("下载失败，%d 秒后重试：%s", delay, exc)
                time_module.sleep(delay)
    raise RuntimeError(f"Copernicus Marine download failed: {last_error}") from last_error


def download_dates(dates: Iterable[date], **kwargs: object) -> list[CopernicusDownloadResult]:
    return [download_scene(target_date, **kwargs) for target_date in dates]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=parse_date, help="single date (YYYY-MM-DD)")
    parser.add_argument("--start", type=parse_date, help="inclusive start date")
    parser.add_argument("--end", type=parse_date, help="inclusive end date")
    parser.add_argument("--hour", type=int, default=12, help="UTC hour for each daily scene")
    parser.add_argument("--south", type=float, default=60.0)
    parser.add_argument("--north", type=float, default=90.0)
    parser.add_argument("--west", type=float, default=-180.0)
    parser.add_argument("--east", type=float, default=180.0)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--data-root", type=Path, help="PolarData root; overrides configured default output")
    parser.add_argument("--credentials-file", type=Path)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def _configure_console_encoding() -> None:
    """Keep Chinese status messages readable in Unicode Windows project paths."""

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    _configure_console_encoding()
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        dates = build_dates(args.date, args.start, args.end)
        output_directory = resolve_output_directory(args.data_root, args.output_dir)
        if args.dry_run:
            for target_date in dates:
                print(
                    f"{PRODUCT_ID} | {DATASET_ID} | {requested_instant(target_date, args.hour).isoformat()} "
                    f"| {','.join(VARIABLES)} | {output_path(target_date, output_directory)}"
                )
            return 0
        if args.credentials_file is None and not credentials_available():
            raise RuntimeError(
                "未找到 Copernicus Marine 凭据。请设置 "
                "COPERNICUSMARINE_SERVICE_USERNAME/COPERNICUSMARINE_SERVICE_PASSWORD，"
                "或先运行 copernicusmarine login。"
            )
        results = download_dates(
            dates,
            output_directory=output_directory,
            hour=args.hour,
            south=args.south,
            north=args.north,
            west=args.west,
            east=args.east,
            retries=args.retries,
            credentials_file=args.credentials_file,
        )
        for result in results:
            print(f"{result.status}: {result.path}")
            print(f"变量映射: {result.variable_map}")
        return 0
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Copernicus 海冰下载失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
