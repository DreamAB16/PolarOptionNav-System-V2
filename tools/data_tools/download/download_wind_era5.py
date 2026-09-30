"""Download small, time-aligned ERA5 hourly u10/v10 monthly subsets."""

from __future__ import annotations

import argparse
from calendar import monthrange
import os
from pathlib import Path
import sys

from netCDF4 import num2date

from core.config.environment_config import get_dataset_path
from core.netcdf import open_netcdf


DATASET = "reanalysis-era5-single-levels"
VARIABLES = ["10m_u_component_of_wind", "10m_v_component_of_wind"]
DEFAULT_OUTPUT = get_dataset_path("wind") / "raw"
HOURS = [f"{hour:02d}:00" for hour in range(24)]


def resolve_output_directory(data_root: Path | None, output_directory: Path | None) -> Path:
    """Resolve an explicit PolarData root without embedding it in the tool."""

    if output_directory is not None:
        return output_directory
    return data_root / "environment" / "wind" / "raw" if data_root else DEFAULT_OUTPUT


def request_for_month(month: str, days: list[int] | None = None) -> dict[str, object]:
    if len(month) != 6 or not month.isdigit():
        raise ValueError("month must use YYYYMM format")
    year, month_number = int(month[:4]), int(month[4:])
    if month_number not in (2, 8) or year != 2025:
        raise ValueError("This test dataset supports only 202502 and 202508.")
    last_day = monthrange(year, month_number)[1]
    selected_days = days or [15]
    if any(day < 1 or day > last_day for day in selected_days):
        raise ValueError(f"day must be between 1 and {last_day}")
    return {
        "product_type": "reanalysis",
        "variable": VARIABLES,
        "year": str(year),
        "month": f"{month_number:02d}",
        "day": [f"{day:02d}" for day in selected_days],
        "time": HOURS,
        "area": [90, -180, 30, 180],
        "data_format": "netcdf",
        "download_format": "unarchived",
    }


def covered_days(path: Path) -> set[int]:
    """Return UTC day numbers represented by an existing ERA5 monthly file."""

    with open_netcdf(path) as dataset:
        time_name = "valid_time" if "valid_time" in dataset.variables else "time"
        if time_name not in dataset.variables:
            raise ValueError(f"ERA5 file has no time coordinate: {path}")
        variable = dataset.variables[time_name]
        values = num2date(
            variable[:], units=variable.units,
            calendar=getattr(variable, "calendar", "standard"),
            only_use_cftime_datetimes=False,
        )
        return {value.day for value in values}


def download_month(month: str, output_directory: Path = DEFAULT_OUTPUT, *, days: list[int] | None = None, client_factory=None) -> Path:
    """Fetch the requested month/day window without discarding a complete file.

    CDS delivers one NetCDF response per request.  If an older sample only
    covers a subset of the requested days, a complete replacement is first
    downloaded to ``.part`` and validated by its time coordinate, then atomically
    published.  This preserves the existing valid data until the expanded file
    is complete.
    """

    destination = output_directory / f"ERA5_wind_{month}.nc"
    requested_days = set(days or [15])
    if destination.is_file() and requested_days.issubset(covered_days(destination)):
        return destination
    if client_factory is None:
        if not (Path.home() / ".cdsapirc").is_file() and not os.getenv("CDSAPI_KEY"):
            raise RuntimeError(
                "未找到 CDS 认证配置。请按 CDS 官方说明配置用户目录下的 .cdsapirc。"
            )
        try:
            import cdsapi
        except ImportError as exc:
            raise RuntimeError("Install cdsapi in the data-tools environment first.") from exc
        client_factory = lambda: cdsapi.Client(timeout=60, retry_max=3, sleep_max=10)
    output_directory.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    if temporary.exists():
        # A completed temporary response can be atomically published on a
        # later invocation (for example after a Windows service releases the
        # old monthly file).  A truncated CDS response must be restarted.
        try:
            if requested_days.issubset(covered_days(temporary)):
                temporary.replace(destination)
                return destination
        except PermissionError as exc:
            raise RuntimeError(
                f"Expanded ERA5 file is complete but {destination} is locked. "
                "Stop/restart the process holding it, then rerun this command to publish the .part file."
            ) from exc
        temporary.unlink()
    try:
        client = client_factory()
        client.retrieve(DATASET, request_for_month(month, days), str(temporary))
        if not temporary.is_file() or temporary.stat().st_size == 0:
            raise RuntimeError(f"CDS did not create a valid file: {temporary}")
        if not requested_days.issubset(covered_days(temporary)):
            raise RuntimeError(f"CDS response does not cover requested days: {sorted(requested_days)}")
        temporary.replace(destination)
    except Exception as exc:
        raise RuntimeError(
            "CDS请求失败；请检查本机 .cdsapirc、网络连接，并确认已接受ERA5数据许可。"
            f" 部分文件保留在：{temporary}"
        ) from exc
    return destination


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--month", choices=("202502", "202508"), required=True)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--data-root", type=Path, help="PolarData root; overrides configured default output")
    parser.add_argument("--days", default="15", help="comma-separated UTC days to request (default: 15)")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        days = [int(value) for value in args.days.split(",") if value.strip()]
        request = request_for_month(args.month, days)
        if args.dry_run:
            output_directory = resolve_output_directory(args.data_root, args.output_dir)
            print(f"{DATASET} | {args.month} | area={request['area']} | variables={','.join(VARIABLES)} | output={output_directory / f'ERA5_wind_{args.month}.nc'}")
            return 0
        print(download_month(args.month, resolve_output_directory(args.data_root, args.output_dir), days=days))
        return 0
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"ERA5 风场下载失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
