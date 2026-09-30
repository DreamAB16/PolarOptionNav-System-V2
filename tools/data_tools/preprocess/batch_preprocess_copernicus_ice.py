"""Batch-compress existing neXtSIM-F daily scenes for the runtime ice provider."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
import sys

from core.config.environment_config import get_dataset_path
from .preprocess_copernicus_ice import (
    PreprocessResult,
    PreprocessValidation,
    default_output_path,
    preprocess_copernicus_ice,
    validate_processed_copernicus_ice,
)


DEFAULT_RAW_DIRECTORY = get_dataset_path("ice") / "raw" / "copernicus"
DEFAULT_OUTPUT_DIRECTORY = get_dataset_path("ice") / "processed" / "copernicus"


@dataclass(frozen=True)
class BatchItem:
    date: date
    status: str
    result: PreprocessResult | None
    validation: PreprocessValidation


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD") from error


def build_dates(start: date, end: date) -> list[date]:
    if start > end:
        raise ValueError("start must not be later than end")
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def process_dates(
    dates: list[date],
    *,
    raw_directory: Path = DEFAULT_RAW_DIRECTORY,
    output_directory: Path = DEFAULT_OUTPUT_DIRECTORY,
    overwrite: bool = False,
) -> list[BatchItem]:
    """Process or validate a daily range, leaving valid outputs untouched."""

    items: list[BatchItem] = []
    for target_date in dates:
        source = raw_directory / f"arctic_ice_{target_date:%Y%m%d}.nc"
        if not source.is_file():
            raise FileNotFoundError(f"Raw Copernicus scene is missing: {source}")
        destination = default_output_path(source, output_directory)
        result: PreprocessResult | None = None
        status = "skipped"
        if not destination.is_file() or overwrite:
            result = preprocess_copernicus_ice(source, destination)
            status = "processed"
        validation = validate_processed_copernicus_ice(source, destination)
        items.append(BatchItem(target_date, status, result, validation))
    return items


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", required=True, type=parse_date)
    parser.add_argument("--end", required=True, type=parse_date)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIRECTORY)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIRECTORY)
    parser.add_argument("--overwrite", action="store_true", help="recreate valid existing outputs")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        items = process_dates(
            build_dates(args.start, args.end),
            raw_directory=args.raw_dir,
            output_directory=args.output_dir,
            overwrite=args.overwrite,
        )
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Copernicus 海冰批量预处理失败：{error}", file=sys.stderr)
        return 1
    processed = [item for item in items if item.status == "processed"]
    skipped = [item for item in items if item.status == "skipped"]
    print(f"输出目录：{args.output_dir.resolve()}")
    print(f"处理：{len(processed)}，已验证跳过：{len(skipped)}，合计：{len(items)}")
    for item in items:
        if item.result is None:
            print(f"{item.date:%Y-%m-%d} {item.status} | 验证={item.validation.samples_per_variable}点/变量")
        else:
            print(
                f"{item.date:%Y-%m-%d} {item.status} | "
                f"{item.result.input_size_bytes} → {item.result.output_size_bytes} bytes | "
                f"验证={item.validation.samples_per_variable}点/变量"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
