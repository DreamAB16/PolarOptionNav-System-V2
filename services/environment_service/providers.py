"""Format-agnostic environmental provider contracts and non-ice adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from functools import lru_cache
from io import BytesIO
from math import atan, ceil, degrees, pi, sinh
from pathlib import Path
from threading import RLock

import numpy as np
from netCDF4 import Dataset, Variable
from PIL import Image

from core.models import BathymetryState, Position, SeaIceState


def _ice_query_arguments(
    position: Position | float,
    timestamp: datetime | float | None,
    legacy_timestamp: datetime | None,
) -> tuple[float, float, datetime | None]:
    """Accept the unified position/time contract while retaining scalar callers."""

    if isinstance(position, Position):
        if timestamp is not None and not isinstance(timestamp, datetime):
            raise TypeError("Ice query timestamp must be a datetime when position is supplied.")
        return position.latitude, position.longitude, timestamp
    if not isinstance(position, (int, float)) or not isinstance(timestamp, (int, float)):
        raise TypeError("Legacy ice query requires latitude, longitude and optional timestamp.")
    return float(position), float(timestamp), legacy_timestamp


class EnvironmentProvider(ABC):
    """Contract implemented by every environmental data source."""

    @abstractmethod
    def get_metadata(self) -> dict[str, object]:
        """Describe readiness without exposing storage details."""

    @abstractmethod
    def get_available_layers(self) -> list[dict[str, str]]:
        """List layers published by this provider."""

    def query(self, position: Position, timestamp: datetime) -> object:
        raise NotImplementedError(f"{type(self).__name__} does not provide time-aware queries.")


class PendingEnvironmentProvider(EnvironmentProvider):
    """Registered environmental source awaiting a real adapter."""

    layer_id: str
    layer_name: str

    def get_metadata(self) -> dict[str, object]:
        return {"provider": self.layer_id, "status": "pending", "layer_count": 1}

    def get_available_layers(self) -> list[dict[str, str]]:
        return [{"id": self.layer_id, "name": self.layer_name, "status": "pending"}]


class BathymetryProvider(PendingEnvironmentProvider, ABC):
    """Format-independent bathymetry point and raster contract."""

    layer_id = "bathymetry"
    layer_name = "Bathymetry"

    @abstractmethod
    def query(self, latitude: float, longitude: float) -> BathymetryState:
        """Return positive-down water depth at one WGS84 coordinate."""

    @abstractmethod
    def get_tile(self, zoom: int, x: int, y: int) -> bytes:
        """Return one 256×256 XYZ PNG tile."""


class RealBathymetryProvider(BathymetryProvider):
    """GEBCO NetCDF adapter that keeps one lazy Dataset handle per process."""

    source_name = "GEBCO_2026_sub_ice"
    max_tile_zoom = 14

    def __init__(self, dataset_path: Path) -> None:
        if not dataset_path.is_file():
            raise FileNotFoundError("Configured bathymetry dataset is unavailable.")
        self._lock = RLock()
        try:
            netcdf_path = dataset_path.resolve().relative_to(Path.cwd().resolve())
        except ValueError:
            netcdf_path = dataset_path
        self._dataset = Dataset(str(netcdf_path), mode="r")
        self._latitude = self._find_coordinate("Y", "latitude")
        self._longitude = self._find_coordinate("X", "longitude")
        self._elevation = self._find_elevation()
        self._validate_grid()
        self._lat_first = float(self._latitude[0])
        self._lon_first = float(self._longitude[0])
        self._lat_step = float(self._latitude[1] - self._latitude[0])
        self._lon_step = float(self._longitude[1] - self._longitude[0])

    def get_metadata(self) -> dict[str, object]:
        return {
            "provider": self.layer_id,
            "status": "ready",
            "source": self.source_name,
            "crs": "EPSG:4326",
            "latitude_range": [float(self._latitude[0]), float(self._latitude[-1])],
            "longitude_range": [float(self._longitude[0]), float(self._longitude[-1])],
            "resolution_degrees": [abs(self._lat_step), abs(self._lon_step)],
            "depth_units": "m",
        }

    def get_available_layers(self) -> list[dict[str, str]]:
        return [{"id": self.layer_id, "name": self.layer_name, "status": "ready"}]

    def query(self, latitude: float, longitude: float) -> BathymetryState:
        lat_index = self._nearest_index(latitude, self._lat_first, self._lat_step, len(self._latitude))
        lon_index = self._nearest_index(longitude, self._lon_first, self._lon_step, len(self._longitude))
        return BathymetryState(
            latitude=latitude,
            longitude=longitude,
            depth=self._read_depth(lat_index, lon_index),
            timestamp=datetime.now(timezone.utc),
            source=self.source_name,
        )

    @lru_cache(maxsize=4096)
    def _read_depth(self, latitude_index: int, longitude_index: int) -> float:
        with self._lock:
            elevation = float(self._elevation[latitude_index, longitude_index])
        return max(0.0, -elevation)

    @lru_cache(maxsize=256)
    def get_tile(self, zoom: int, x: int, y: int) -> bytes:
        if zoom < 0 or zoom > self.max_tile_zoom:
            raise ValueError(f"Tile zoom must be between 0 and {self.max_tile_zoom}.")
        tile_count = 1 << zoom
        if x < 0 or y < 0 or x >= tile_count or y >= tile_count:
            raise ValueError("Tile coordinate is outside the requested zoom level.")
        west = x / tile_count * 360.0 - 180.0
        east = (x + 1) / tile_count * 360.0 - 180.0
        north = degrees(atan(sinh(pi * (1.0 - 2.0 * y / tile_count))))
        south = degrees(atan(sinh(pi * (1.0 - 2.0 * (y + 1) / tile_count))))
        return self._render_depth_png(self._read_window(south, west, north, east))

    def close(self) -> None:
        with self._lock:
            if self._dataset.isopen():
                self._dataset.close()

    def _read_window(self, south: float, west: float, north: float, east: float) -> np.ndarray:
        south_index = self._nearest_index(south, self._lat_first, self._lat_step, len(self._latitude))
        north_index = self._nearest_index(north, self._lat_first, self._lat_step, len(self._latitude))
        west_index = self._nearest_index(west, self._lon_first, self._lon_step, len(self._longitude))
        east_index = self._nearest_index(east, self._lon_first, self._lon_step, len(self._longitude))
        lat_low, lat_high = sorted((south_index, north_index))
        lon_low, lon_high = sorted((west_index, east_index))
        lat_stride = max(1, ceil((lat_high - lat_low + 1) / 256))
        lon_stride = max(1, ceil((lon_high - lon_low + 1) / 256))
        with self._lock:
            values = np.ma.asarray(
                self._elevation[lat_low : lat_high + 1 : lat_stride, lon_low : lon_high + 1 : lon_stride]
            )
        return np.flipud(values)

    @staticmethod
    def _render_depth_png(elevations: np.ndarray) -> bytes:
        masked = np.ma.asarray(elevations, dtype=np.float32)
        values = np.asarray(masked.filled(np.nan), dtype=np.float32)
        water = (~np.ma.getmaskarray(masked)) & np.isfinite(values) & (values < 0)
        depth = np.maximum(-values, 0.0)
        render_depth = np.where(water, depth, 0.0)
        scale = np.clip(np.log1p(render_depth) / np.log1p(6000.0), 0, 1)
        rgba = np.zeros((*values.shape, 4), dtype=np.uint8)
        rgba[..., 0] = (105 - 90 * scale).astype(np.uint8)
        rgba[..., 1] = (205 - 135 * scale).astype(np.uint8)
        rgba[..., 2] = (235 - 95 * scale).astype(np.uint8)
        rgba[..., 3] = np.where(water, 175, 0).astype(np.uint8)
        # Keep masked source cells transparent instead of blending them into
        # neighbouring water pixels during downsampling.
        image = Image.fromarray(rgba, mode="RGBA").resize((256, 256), Image.Resampling.NEAREST)
        output = BytesIO()
        image.save(output, format="PNG", optimize=True)
        return output.getvalue()

    def _find_coordinate(self, axis: str, standard_name: str) -> Variable:
        for variable in self._dataset.variables.values():
            if getattr(variable, "axis", None) == axis or getattr(variable, "standard_name", None) == standard_name:
                return variable
        raise ValueError(f"Bathymetry dataset has no {standard_name} coordinate.")

    def _find_elevation(self) -> Variable:
        for variable in self._dataset.variables.values():
            if getattr(variable, "standard_name", None) == "height_above_mean_sea_level":
                return variable
        raise ValueError("Bathymetry dataset has no elevation variable.")

    def _validate_grid(self) -> None:
        if self._latitude.ndim != 1 or self._longitude.ndim != 1:
            raise ValueError("Bathymetry coordinates must be one-dimensional.")
        if self._elevation.dimensions != (self._latitude.dimensions[0], self._longitude.dimensions[0]):
            raise ValueError("Bathymetry elevation dimensions do not match latitude/longitude.")
        if getattr(self._elevation, "units", None) != "m":
            raise ValueError("Bathymetry elevation must use metres.")

    @staticmethod
    def _nearest_index(value: float, first: float, step: float, size: int) -> int:
        return min(max(round((value - first) / step), 0), size - 1)


class IceProvider(PendingEnvironmentProvider, ABC):
    """Source-independent sea-ice point-query contract."""

    layer_id = "ice"
    layer_name = "Sea Ice"

    @abstractmethod
    def query(
        self,
        position: Position | float,
        timestamp: datetime | float | None = None,
        legacy_timestamp: datetime | None = None,
    ) -> SeaIceState:
        """Return sea ice for a WGS84 position and optional UTC time."""


class MockIceProvider(IceProvider):
    """Deterministic provider used by isolated service tests."""

    def query(
        self,
        position: Position | float,
        timestamp: datetime | float | None = None,
        legacy_timestamp: datetime | None = None,
    ) -> SeaIceState:
        latitude, longitude, requested_time = _ice_query_arguments(position, timestamp, legacy_timestamp)
        return SeaIceState(
            latitude=latitude,
            longitude=longitude,
            timestamp=requested_time or datetime.now(timezone.utc),
            concentration=0.78,
            thickness=1.2,
            source="mock",
        )


class WindProvider(PendingEnvironmentProvider):
    layer_id = "wind"
    layer_name = "Wind"


class CurrentProvider(PendingEnvironmentProvider):
    layer_id = "current"
    layer_name = "Current"


class WaveProvider(PendingEnvironmentProvider):
    layer_id = "wave"
    layer_name = "Wave"
