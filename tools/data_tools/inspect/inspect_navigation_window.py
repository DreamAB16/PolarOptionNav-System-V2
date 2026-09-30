"""Audit raw environmental files against one continuous UTC navigation window.

The tool is deliberately offline-only: it neither imports application services
nor alters data.  It reports file identity, temporal coverage, coordinates,
variables, missing-data ratios, and SHA256 checksums for a requested window.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
from netCDF4 import num2date

from core.netcdf import open_netcdf


ROOT = Path("data/environment")
SPECS: dict[str, dict[str, Any]] = {
    "wind": {
        "directory": ROOT / "wind" / "raw",
        "pattern": "ERA5_wind_*.nc",
        "variables": (("u10", "10m_u_component_of_wind"), ("v10", "10m_v_component_of_wind")),
    },
    "current": {
        "directory": ROOT / "current" / "raw",
        "pattern": "Copernicus_current_*.nc",
        "variables": (("vxo",), ("vyo",)),
    },
    "wave": {
        "directory": ROOT / "wave" / "raw",
        "pattern": "Copernicus_wave_*.nc",
        "variables": (("VHM0",), ("VTPK",), ("VMDR",)),
    },
    "ice": {
        "directory": ROOT / "ice" / "raw" / "copernicus",
        "pattern": "arctic_ice_*.nc",
        "variables": (("siconc",), ("sithick",), ("siconc_my",), ("siconc_young",)),
    },
}


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _times(dataset: Any) -> list[datetime]:
    for name in ("time", "valid_time"):
        if name in dataset.variables:
            variable = dataset.variables[name]
            return [_utc(value) for value in num2date(
                variable[:], units=variable.units,
                calendar=getattr(variable, "calendar", "standard"),
                only_use_cftime_datetimes=False,
            )]
    raise ValueError("Dataset has no time/valid_time coordinate.")


def _coordinate_range(dataset: Any) -> dict[str, object]:
    report: dict[str, object] = {}
    for aliases in (("latitude", "lat"), ("longitude", "lon"), ("x",), ("y",)):
        name = next((candidate for candidate in aliases if candidate in dataset.variables), None)
        if name is None:
            continue
        values = np.asarray(dataset.variables[name][:], dtype=np.float64)
        finite = values[np.isfinite(values)]
        if finite.size:
            item: dict[str, object] = {
                "name": name,
                "shape": list(values.shape),
                "min": float(finite.min()),
                "max": float(finite.max()),
                "units": getattr(dataset.variables[name], "units", None),
            }
            if values.ndim == 1 and values.size > 1:
                item["resolution"] = float(np.median(np.abs(np.diff(values))))
            report[aliases[0]] = item
    return report


def _quality(variable: Any) -> dict[str, float | int]:
    """Count valid values in time slabs so full files never enter memory."""

    time_axis = variable.dimensions.index("time") if "time" in variable.dimensions else None
    indices = range(variable.shape[time_axis]) if time_axis is not None else range(1)
    total = valid = 0
    for index in indices:
        selector: list[object] = [slice(None)] * variable.ndim
        if time_axis is not None:
            selector[time_axis] = index
        values = np.ma.masked_invalid(np.ma.asarray(variable[tuple(selector)], dtype=np.float64))
        total += int(values.size)
        valid += int(values.count())
    return {
        "valid_count": valid,
        "nodata_count": total - valid,
        "valid_ratio": valid / total if total else 0.0,
        "nodata_ratio": (total - valid) / total if total else 0.0,
    }


def inspect_file(path: Path, expected_variables: tuple[tuple[str, ...], ...]) -> dict[str, object]:
    with open_netcdf(path) as dataset:
        resolved = []
        for aliases in expected_variables:
            name = next((candidate for candidate in aliases if candidate in dataset.variables), None)
            if name is None:
                raise ValueError(f"{path.name} is missing one of: {', '.join(aliases)}")
            variable = dataset.variables[name]
            resolved.append({
                "name": name,
                "dtype": str(variable.dtype),
                "units": getattr(variable, "units", None),
                "dimensions": list(variable.dimensions),
                **_quality(variable),
            })
        times = _times(dataset)
        interval = (times[1] - times[0]).total_seconds() if len(times) > 1 else None
        return {
            "path": str(path.resolve()),
            "size_bytes": path.stat().st_size,
            "size_mib": round(path.stat().st_size / 1024 ** 2, 2),
            "sha256": _sha256(path),
            "format": {"data_model": dataset.data_model, "disk_format": dataset.disk_format},
            "dimensions": {name: len(value) for name, value in dataset.dimensions.items()},
            "time": {
                "first": times[0].isoformat(), "last": times[-1].isoformat(),
                "count": len(times), "interval_seconds": interval,
                "hourly": interval == 3600.0,
            },
            "coordinates": _coordinate_range(dataset),
            "variables": resolved,
        }


def audit(start: datetime, end: datetime, root: Path = ROOT) -> dict[str, object]:
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("start/end must be ISO-8601 UTC timestamps with an offset.")
    start, end = _utc(start), _utc(end)
    if start > end:
        raise ValueError("start must not be later than end")
    datasets: dict[str, object] = {}
    required_hours = int((end - start).total_seconds() // 3600) + 1
    for name, spec in SPECS.items():
        directory = root / Path(spec["directory"]).relative_to(ROOT)
        files = sorted(directory.glob(spec["pattern"])) if directory.is_dir() else []
        reports = [inspect_file(path, spec["variables"]) for path in files]
        in_window = [
            report for report in reports
            if datetime.fromisoformat(str(report["time"]["last"])) >= start
            and datetime.fromisoformat(str(report["time"]["first"])) <= end
        ]
        covered: set[datetime] = set()
        for report in in_window:
            first = datetime.fromisoformat(str(report["time"]["first"]))
            last = datetime.fromisoformat(str(report["time"]["last"]))
            if bool(report["time"]["hourly"]):
                cursor = max(first, start)
                while cursor <= min(last, end):
                    covered.add(cursor)
                    cursor += timedelta(hours=1)
            elif name == "ice" and start.date() <= first.date() <= end.date():
                # neXtSIM scenes are daily snapshots (currently 12:00 UTC),
                # not a 24-hour field series.
                covered.add(first)
        expected = required_hours if name != "ice" else (end.date() - start.date()).days + 1
        actual = len(covered) if name != "ice" else len({item.date() for item in covered})
        datasets[name] = {
            "files": in_window,
            "coverage": {
                "expected": expected,
                "actual": actual,
                "complete": actual == expected,
                "note": "hourly" if name != "ice" else "daily 12:00 UTC scene",
            },
        }
    return {
        "window": {"start": start.isoformat(), "end": end.isoformat(), "expected_hourly_steps": required_hours},
        "datasets": datasets,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", required=True, type=datetime.fromisoformat)
    parser.add_argument("--end", required=True, type=datetime.fromisoformat)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = audit(args.start, args.end, args.root)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
