"""Inspect Copernicus Marine Arctic wave NetCDF files and write a report."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import numpy as np
from netCDF4 import num2date

from core.netcdf import open_netcdf


PRODUCT_ID = "ARCTIC_ANALYSIS_FORECAST_WAV_002_014"
DATASET_ID = "dataset-wam-arctic-1hr3km-be"
VARIABLES = ("VHM0", "VTPK", "VMDR")
SAMPLE_TARGETS = {
    "巴伦支海": (80.0, 30.0),
    "格陵兰海": (75.0, -30.0),
    "白令海峡": (65.0, -170.0),
}
ANOMALY_RANGES = {
    "VHM0": (0.0, 40.0),
    "VTPK": (0.0, 40.0),
    "VMDR": (0.0, 360.0),
}


def _json_value(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    return value


def _variable_attributes(variable: Any) -> dict[str, object]:
    names = (
        "standard_name", "long_name", "units", "_FillValue", "missing_value",
        "valid_min", "valid_max", "grid_mapping", "coordinates",
    )
    available = set(variable.ncattrs())
    return {name: _json_value(variable.getncattr(name)) for name in names if name in available}


def _times(dataset: Any) -> list[datetime]:
    variable = dataset.variables["time"]
    values = num2date(
        variable[:],
        units=variable.units,
        calendar=getattr(variable, "calendar", "standard"),
        only_use_cftime_datetimes=False,
    )
    return [
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
        for value in values
    ]


def _coordinate_report(dataset: Any) -> tuple[dict[str, object], str]:
    report: dict[str, object] = {}
    if "latitude" in dataset.variables and "longitude" in dataset.variables:
        for name in ("latitude", "longitude"):
            variable = dataset.variables[name]
            values = np.asarray(variable[:], dtype=np.float64)
            finite = values[np.isfinite(values)]
            item: dict[str, object] = {
                "shape": list(values.shape),
                "min": float(finite.min()),
                "max": float(finite.max()),
                "units": getattr(variable, "units", None),
            }
            if values.ndim == 1 and values.size > 1:
                item["resolution"] = float(np.median(np.abs(np.diff(values))))
            report[name] = item
        return report, "geographic_latitude_longitude"
    if "x" in dataset.variables and "y" in dataset.variables:
        for name in ("x", "y"):
            variable = dataset.variables[name]
            values = np.asarray(variable[:], dtype=np.float64)
            report[name] = {
                "size": int(values.size),
                "min": float(np.nanmin(values)),
                "max": float(np.nanmax(values)),
                "resolution": float(np.median(np.abs(np.diff(values)))) if values.size > 1 else None,
                "units": getattr(variable, "units", None),
            }
        return report, "projected_xy"
    raise ValueError("Wave file has neither latitude/longitude nor x/y coordinates.")


def _quality(dataset: Any, name: str) -> dict[str, object]:
    variable = dataset.variables[name]
    total = 0
    valid = 0
    anomaly_count = 0
    value_sum = 0.0
    minimum = float("inf")
    maximum = float("-inf")
    lower, upper = ANOMALY_RANGES[name]
    time_axis = variable.dimensions.index("time") if "time" in variable.dimensions else None
    slices = range(variable.shape[time_axis]) if time_axis is not None else range(1)
    for index in slices:
        selection: list[object] = [slice(None)] * variable.ndim
        if time_axis is not None:
            selection[time_axis] = index
        values = np.ma.masked_invalid(np.ma.asarray(variable[tuple(selection)], dtype=np.float64))
        data = values.compressed()
        total += int(values.size)
        valid += int(data.size)
        if data.size:
            minimum = min(minimum, float(data.min()))
            maximum = max(maximum, float(data.max()))
            value_sum += float(data.sum(dtype=np.float64))
            anomaly_count += int(np.count_nonzero((data < lower) | (data > upper)))
    report = {
        "dtype": str(variable.dtype),
        **_variable_attributes(variable),
        "min": minimum if valid else None,
        "max": maximum if valid else None,
        "mean": value_sum / valid if valid else None,
        "valid_count": valid,
        "nodata_count": total - valid,
        "valid_ratio": valid / total if total else 0.0,
        "nodata_ratio": (total - valid) / total if total else 0.0,
        "anomaly_range": [lower, upper],
        "anomaly_count": anomaly_count,
    }
    if name == "VMDR":
        report["mean_note"] = "Arithmetic diagnostic only; use a circular mean for directional analysis."
    return report


def _nearest_sample_indices(dataset: Any, latitude: float, longitude: float) -> tuple[int, int]:
    lat_values = np.asarray(dataset.variables["latitude"][:], dtype=np.float64)
    lon_values = np.asarray(dataset.variables["longitude"][:], dtype=np.float64)
    if lat_values.ndim == lon_values.ndim == 1:
        row = int(np.argmin(np.abs(lat_values - latitude)))
        lon_delta = (lon_values - longitude + 180.0) % 360.0 - 180.0
        column = int(np.argmin(np.abs(lon_delta)))
        return row, column
    if lat_values.shape != lon_values.shape or lat_values.ndim != 2:
        raise ValueError("Unsupported wave latitude/longitude coordinate layout.")
    lon_delta = (lon_values - longitude + 180.0) % 360.0 - 180.0
    distance = (lat_values - latitude) ** 2 + (lon_delta * np.cos(np.deg2rad(latitude))) ** 2
    return tuple(int(value) for value in np.unravel_index(np.nanargmin(distance), distance.shape))


def _sample_value(variable: Any, time_index: int, row: int, column: int) -> float | None:
    indices: list[int] = []
    for dimension in variable.dimensions:
        if dimension == "time":
            indices.append(time_index)
        elif dimension in ("latitude", "y"):
            indices.append(row)
        elif dimension in ("longitude", "x"):
            indices.append(column)
        elif len(variable.group().dimensions[dimension]) == 1:
            indices.append(0)
        else:
            raise ValueError(f"Unsupported dimension {dimension!r} in {variable.name!r}.")
    value = variable[tuple(indices)]
    if np.ma.is_masked(value) or not np.isfinite(float(value)):
        return None
    return float(value)


def inspect_wave(path: str | Path) -> dict[str, object]:
    nc_path = Path(path)
    with open_netcdf(nc_path) as dataset:
        missing = set(VARIABLES).difference(dataset.variables)
        if missing:
            raise ValueError(f"Wave file is missing: {', '.join(sorted(missing))}")
        times = _times(dataset)
        coordinate_report, coordinate_kind = _coordinate_report(dataset)
        interval_seconds = (times[1] - times[0]).total_seconds() if len(times) > 1 else None
        grid_mappings = sorted({
            str(getattr(dataset.variables[name], "grid_mapping"))
            for name in VARIABLES
            if getattr(dataset.variables[name], "grid_mapping", None)
        })
        mapping_variables = {
            name: {attribute: _json_value(variable.getncattr(attribute)) for attribute in variable.ncattrs()}
            for name, variable in dataset.variables.items()
            if name in grid_mappings
        }
        projection_attributes = {
            name: _json_value(dataset.getncattr(name))
            for name in dataset.ncattrs()
            if any(token in name.lower() for token in ("proj", "crs", "stereo"))
        }
        noon_index = min(range(len(times)), key=lambda index: abs(times[index].hour - 12))
        samples = []
        if "latitude" in dataset.variables and "longitude" in dataset.variables:
            for region, (target_lat, target_lon) in SAMPLE_TARGETS.items():
                row, column = _nearest_sample_indices(dataset, target_lat, target_lon)
                latitude_variable = dataset.variables["latitude"]
                longitude_variable = dataset.variables["longitude"]
                actual_lat = float(latitude_variable[row] if latitude_variable.ndim == 1 else latitude_variable[row, column])
                actual_lon = float(longitude_variable[column] if longitude_variable.ndim == 1 else longitude_variable[row, column])
                samples.append({
                    "region": region,
                    "requested_latitude": target_lat,
                    "requested_longitude": target_lon,
                    "latitude": actual_lat,
                    "longitude": actual_lon,
                    "time": times[noon_index].isoformat(),
                    **{
                        name: _sample_value(dataset.variables[name], noon_index, row, column)
                        for name in VARIABLES
                    },
                })
        variable_reports = {name: _quality(dataset, name) for name in VARIABLES}
        return {
            "file": {
                "path": str(nc_path.resolve()),
                "size_bytes": nc_path.stat().st_size,
                "size_mib": nc_path.stat().st_size / 1024**2,
                "data_model": dataset.data_model,
                "disk_format": dataset.disk_format,
            },
            "dimensions": {name: len(value) for name, value in dataset.dimensions.items()},
            "time": {
                "first_time": times[0].isoformat(),
                "last_time": times[-1].isoformat(),
                "count": len(times),
                "interval_seconds": interval_seconds,
                "hourly": interval_seconds == 3600.0,
            },
            "coordinates": coordinate_report,
            "crs": {
                "coordinate_kind": coordinate_kind,
                "grid_mapping_attributes": grid_mappings,
                "grid_mapping_variables": mapping_variables,
                "projection_global_attributes": projection_attributes,
                "proj4": next((str(value.get("proj4")) for value in mapping_variables.values() if value.get("proj4")), None),
                "polar_stereographic": any(
                    "stere" in str(value).lower()
                    for value in [*grid_mappings, *mapping_variables.values(), *projection_attributes.values()]
                ),
            },
            "variables": variable_reports,
            "samples": samples,
            "global_attributes": {name: _json_value(dataset.getncattr(name)) for name in dataset.ncattrs()},
        }


def write_readme(reports: list[dict[str, object]], path: Path) -> None:
    lines = [
        "# Copernicus Marine 北极海浪数据",
        "",
        f"- 数据来源：Copernicus Marine Arctic Ocean Wave Analysis and Forecast",
        f"- Product ID：`{PRODUCT_ID}`",
        f"- Dataset ID：`{DATASET_ID}`",
        "- 官方产品页：https://data.marine.copernicus.eu/product/ARCTIC_ANALYSIS_FORECAST_WAV_002_014/services",
        "- 变量：`VHM0` 有效波高（m）、`VTPK` 峰值周期（s）、`VMDR` 平均来向（degree）",
        "- 请求范围：30°N–90°N、-180°–180°；实际范围以服务覆盖为准",
        "- 投影说明：源WAM模式为North Polar Stereographic；当前Toolbox default Subset交付为0.03°规则经纬网，文件本身不是极射坐标网格",
        "- 方向说明：VMDR的mean按任务要求输出为算术诊断值，方向统计应使用圆均值，不能直接解释算术平均数",
        "",
        "## 文件与质量检查",
        "",
    ]
    for report in reports:
        file_info = report["file"]
        time_info = report["time"]
        crs = report["crs"]
        coordinates = report["coordinates"]
        lines.extend([
            f"### {Path(str(file_info['path'])).name}",
            "",
            f"- 大小：{file_info['size_mib']:.2f} MiB",
            f"- 格式：{file_info['data_model']} / {file_info['disk_format']}",
            f"- 时间：{time_info['first_time']} ～ {time_info['last_time']}，{time_info['count']} 时次，小时级：{'是' if time_info['hourly'] else '否'}",
            f"- 坐标：`{crs['coordinate_kind']}`；Polar Stereographic：{'是' if crs['polar_stereographic'] else '否'}",
            f"- 空间范围：`{json.dumps(coordinates, ensure_ascii=False)}`",
        ])
        for name in VARIABLES:
            variable = report["variables"][name]
            lines.append(
                f"- {name}：min={variable['min']:.6g}, max={variable['max']:.6g}, "
                f"mean={variable['mean']:.6g}, valid={variable['valid_ratio']:.2%}, "
                f"NoData={variable['nodata_ratio']:.2%}, anomalies={variable['anomaly_count']}"
            )
        lines.extend(["", "固定点（约12:00 UTC）抽样：", ""])
        for sample in report["samples"]:
            lines.append(
                f"- {sample['region']} ({sample['latitude']:.3f}, {sample['longitude']:.3f})："
                f"VHM0={sample['VHM0']}, VTPK={sample['VTPK']}, VMDR={sample['VMDR']}"
            )
        lines.append("")
    lines.extend([
        "## 目录语义",
        "",
        "`raw/` 保存未经业务转换的Copernicus Marine下载结果。运行时 RealWaveProvider 直接读取这些文件；本工具不改变数据内容。",
        "",
    ])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--readme", type=Path)
    args = parser.parse_args(argv)
    reports = [inspect_wave(path) for path in args.files]
    if args.readme:
        write_readme(reports, args.readme)
    print(json.dumps(reports, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
