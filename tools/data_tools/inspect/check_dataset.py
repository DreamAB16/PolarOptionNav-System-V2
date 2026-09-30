"""Generic dataset-check entry point for supported navigation data types."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from tools.data_tools.inspect.inspect_nc import DATASET_VARIABLE_ALIASES, inspect_nc


SUPPORTED_DATASETS = tuple(sorted(DATASET_VARIABLE_ALIASES))


def check_dataset(
    dataset_type: str,
    path: str | Path,
    *,
    full_stats: bool = False,
    max_sample_values: int = 1_000_000,
) -> dict[str, Any]:
    """Inspect a dataset through the rule set registered for its logical type."""

    normalized = dataset_type.lower()
    if normalized not in SUPPORTED_DATASETS:
        raise ValueError(
            f"Unsupported dataset type '{dataset_type}'. Supported: {', '.join(SUPPORTED_DATASETS)}"
        )
    report = inspect_nc(
        path,
        dataset_type=normalized,
        full_stats=full_stats,
        max_sample_values=max_sample_values,
    )
    report["dataset_type"] = normalized
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset_type", choices=SUPPORTED_DATASETS)
    parser.add_argument("path", type=Path)
    parser.add_argument("--full-stats", action="store_true")
    parser.add_argument("--max-sample-values", type=int, default=1_000_000)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = check_dataset(
            args.dataset_type,
            args.path,
            full_stats=args.full_stats,
            max_sample_values=args.max_sample_values,
        )
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Dataset check failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

