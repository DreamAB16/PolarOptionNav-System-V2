"""Persistent, fixed 25 km Northeast Passage planning grid.

The grid is indexed in EPSG:3413 from a fixed projected origin.  Its static
fields are built once from the polar GEBCO raster and are never recalculated
by a viewport request.  Dynamic weather/ice risks are deliberately separate.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

import numpy as np
from pyproj import Transformer
import rasterio

from config.settings import NORTHEAST_PASSAGE_REGION, PLANNING_CELL_SIZE_M
from core.config.environment_config import get_dataset_path

GRID_CRS = "EPSG:3413"
STATIC_GRID_VERSION = 3
_TO_POLAR = Transformer.from_crs("EPSG:4326", GRID_CRS, always_xy=True)
_TO_WGS84 = Transformer.from_crs(GRID_CRS, "EPSG:4326", always_xy=True)


def to_planning_lon(longitude: float) -> float:
    """Convert a WGS84 display longitude to the planner's [0, 360] domain."""
    return float(longitude + 360.0 if longitude < 0.0 else longitude)


def to_display_lon(planning_longitude: float) -> float:
    """Convert a planning longitude back to standard WGS84 display form."""
    return float(planning_longitude - 360.0 if planning_longitude > 180.0 else planning_longitude)


def planning_lon_intervals(west: float, east: float) -> list[tuple[float, float]]:
    """Translate a display bbox into one or two continuous planning intervals."""
    if abs(east - west) >= 359.999:
        return [(0.0, 360.0)]
    if west <= east:
        if west < 0.0 <= east:
            return [(to_planning_lon(west), 360.0), (0.0, to_planning_lon(east))]
        return [(to_planning_lon(west), to_planning_lon(east))]
    # west > east is the standard display representation of a bbox crossing
    # the date line, for example 170E through 170W.
    return [(to_planning_lon(west), to_planning_lon(east))]


@dataclass(slots=True)
class StaticPlanningGrid:
    metadata: dict[str, object]
    center_lat: np.ndarray
    center_lon: np.ndarray
    corners_lat: np.ndarray
    corners_lon: np.ndarray
    inside_region: np.ndarray
    is_land: np.ndarray
    land_ratio: np.ndarray
    depth_m: np.ndarray
    static_traversable: np.ndarray

    @property
    def shape(self) -> tuple[int, int]:
        return self.center_lat.shape

    @property
    def height(self) -> int:
        return self.shape[0]

    @property
    def width(self) -> int:
        return self.shape[1]

    def contains(self, latitude: float, longitude: float) -> bool:
        r = self.metadata["region"]
        return r["south"] <= latitude <= r["north"] and r["planning_west"] <= to_planning_lon(longitude) <= r["planning_east"]

    def nearest_cell(self, latitude: float, longitude: float) -> tuple[int, int] | None:
        if not self.contains(latitude, longitude):
            return None
        longitude_delta = ((self.center_lon - longitude + 180.0) % 360.0) - 180.0
        distance = (self.center_lat - latitude) ** 2 + (longitude_delta * np.cos(np.radians(latitude))) ** 2
        distance = np.where(self.inside_region, distance, np.inf)
        y, x = np.unravel_index(np.argmin(distance), distance.shape)
        return int(x), int(y)

    def viewport_indices(self, south: float, north: float, west: float, east: float) -> tuple[np.ndarray, dict[str, object] | None]:
        r = self.metadata["region"]
        clipped_south, clipped_north = max(south, r["south"]), min(north, r["north"])
        intervals = [(max(low, r["planning_west"]), min(high, r["planning_east"])) for low, high in planning_lon_intervals(west, east)]
        intervals = [(low, high) for low, high in intervals if low < high]
        if clipped_south >= clipped_north or not intervals:
            return np.empty((0, 2), dtype=np.int32), None
        # Do not use longitude min/max here: a valid cell at the 180-degree
        # meridian has corners on both +180 and -180 and would otherwise look
        # like a world-wide rectangle.  Compare each centre to the viewport
        # using a wrapped longitude delta plus the real half-cell span.
        latitude_mid = (clipped_south + clipped_north) / 2.0
        latitude_span = np.max(np.abs(self.corners_lat - self.center_lat[..., None]), axis=2)
        center_planning_lon = np.where(self.center_lon < 0.0, self.center_lon + 360.0, self.center_lon)
        corner_planning_lon = np.where(self.corners_lon < 0.0, self.corners_lon + 360.0, self.corners_lon)
        longitude_span = np.max(np.abs(corner_planning_lon - center_planning_lon[..., None]), axis=2)
        longitude_match = np.zeros(self.shape, dtype=bool)
        for low, high in intervals:
            longitude_match |= (center_planning_lon >= low - longitude_span) & (center_planning_lon <= high + longitude_span)
        intersects = self.inside_region & (np.abs(self.center_lat - latitude_mid) <= (clipped_north - clipped_south) / 2.0 + latitude_span) & longitude_match
        return np.argwhere(intersects), {"south": clipped_south, "north": clipped_north, "planning_intervals": intervals, "west": to_display_lon(intervals[0][0]), "east": to_display_lon(intervals[-1][1])}


class StaticGridRepository:
    """Load the generated NEP grid once per process."""

    _instance: StaticPlanningGrid | None = None

    @classmethod
    def artifact_path(cls) -> Path:
        return Path(__file__).resolve().parents[2] / "data" / "planning" / "northeast_passage_25km_static.npz"

    @classmethod
    def load(cls) -> StaticPlanningGrid:
        if cls._instance is None:
            path = cls.artifact_path()
            if not path.is_file():
                build_static_grid(path)
            with np.load(path, allow_pickle=False) as value:
                metadata = json.loads(str(value["metadata"]))
                if metadata.get("version") != STATIC_GRID_VERSION:
                    build_static_grid(path)
                    value.close()
                    return cls.load()
                cls._instance = StaticPlanningGrid(
                    metadata=metadata,
                    center_lat=value["center_lat"], center_lon=value["center_lon"],
                    corners_lat=value["corners_lat"], corners_lon=value["corners_lon"],
                    inside_region=value["inside_region"].astype(bool), is_land=value["is_land"].astype(bool),
                    land_ratio=value["land_ratio"], depth_m=value["depth_m"], static_traversable=value["static_traversable"].astype(bool),
                )
        return cls._instance


def build_static_grid(output: Path | None = None) -> dict[str, object]:
    """Batch-sample GEBCO once and persist static attributes for every cell."""
    output = output or StaticGridRepository.artifact_path()
    output.parent.mkdir(parents=True, exist_ok=True)
    start = perf_counter()
    region = dict(NORTHEAST_PASSAGE_REGION)
    corners = [(region["west"], region["south"]), (region["west"], region["north"]), (region["east"], region["south"]), (region["east"], region["north"])]
    projected = np.asarray([_TO_POLAR.transform(lon, lat) for lon, lat in corners])
    min_x, min_y = projected.min(axis=0); max_x, max_y = projected.max(axis=0)
    # Fixed origin anchors ids independently of all future viewports.
    origin_x = np.floor(min_x / PLANNING_CELL_SIZE_M) * PLANNING_CELL_SIZE_M
    origin_y = np.floor(min_y / PLANNING_CELL_SIZE_M) * PLANNING_CELL_SIZE_M
    width = int(np.ceil((max_x - origin_x) / PLANNING_CELL_SIZE_M))
    height = int(np.ceil((max_y - origin_y) / PLANNING_CELL_SIZE_M))
    cols, rows = np.meshgrid(np.arange(width), np.arange(height))
    center_x = origin_x + (cols + 0.5) * PLANNING_CELL_SIZE_M
    center_y = origin_y + (rows + 0.5) * PLANNING_CELL_SIZE_M
    center_lon, center_lat = _TO_WGS84.transform(center_x, center_y)
    offsets = np.asarray([[-.5, -.5], [.5, -.5], [.5, .5], [-.5, .5]]) * PLANNING_CELL_SIZE_M
    corners_lon = np.empty((height, width, 4), dtype=np.float64); corners_lat = np.empty_like(corners_lon)
    for index, (dx, dy) in enumerate(offsets):
        lon, lat = _TO_WGS84.transform(center_x + dx, center_y + dy)
        corners_lon[:, :, index] = lon; corners_lat[:, :, index] = lat
    center_planning_lon = np.where(center_lon < 0.0, center_lon + 360.0, center_lon)
    inside = (center_lat >= region["south"]) & (center_lat <= region["north"]) & (center_planning_lon >= region["planning_west"]) & (center_planning_lon <= region["planning_east"])
    sample_lon = np.concatenate([center_lon[..., None], corners_lon], axis=2).reshape(-1)
    sample_lat = np.concatenate([center_lat[..., None], corners_lat], axis=2).reshape(-1)
    polar_x, polar_y = _TO_POLAR.transform(sample_lon, sample_lat)
    bathymetry_path = get_dataset_path("bathymetry") / "processed" / "bathymetry_polar_3413.tif"
    if not bathymetry_path.is_file():
        raise FileNotFoundError(f"Static grid requires {bathymetry_path}")
    with rasterio.open(bathymetry_path) as raster:
        samples = np.asarray([value[0] for value in raster.sample(zip(polar_x, polar_y), masked=False)], dtype=float)
        nodata = raster.nodata
    samples = samples.reshape(height, width, 5)
    valid = np.isfinite(samples) & (samples != nodata)
    land_samples = (~valid) | (samples >= 0.0)
    land_ratio = land_samples.mean(axis=2).astype(np.float32)
    is_land = land_ratio >= 0.05
    water_depth = np.where(valid & (samples < 0.0), -samples, np.nan)
    depth_m = np.nanmedian(water_depth, axis=2)
    depth_m = np.where(np.isfinite(depth_m), depth_m, 0.0).astype(np.float32)
    static_traversable = inside & ~is_land & (depth_m > 0.0)
    metadata = {"version": STATIC_GRID_VERSION, "region": region, "cell_size_m": PLANNING_CELL_SIZE_M, "crs": GRID_CRS, "origin_x_m": float(origin_x), "origin_y_m": float(origin_y), "generation": "GEBCO_2026_polar_3413_batch", "build_ms": round((perf_counter() - start) * 1000, 1)}
    np.savez_compressed(output, metadata=json.dumps(metadata), center_lat=center_lat.astype(np.float32), center_lon=center_lon.astype(np.float32), corners_lat=corners_lat.astype(np.float32), corners_lon=corners_lon.astype(np.float32), inside_region=inside, is_land=is_land, land_ratio=land_ratio, depth_m=depth_m, static_traversable=static_traversable)
    return {**metadata, "width": width, "height": height, "total_cells": int(inside.sum()), "sea_cells": int(static_traversable.sum()), "land_cells": int((inside & is_land).sum())}


__all__ = ["GRID_CRS", "StaticGridRepository", "StaticPlanningGrid", "build_static_grid", "to_planning_lon", "to_display_lon", "planning_lon_intervals"]
