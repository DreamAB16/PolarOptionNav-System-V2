"""Unified, read-through environment grid facade.

This module intentionally does not open NetCDF files or alter provider
outputs. It turns the existing fault-isolated environment snapshot into a
stable cell contract and caches sampled cells by time and location.
"""

from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timezone
from threading import RLock

from core.models import EnvironmentCell, EnvironmentState, Position

from .service import EnvironmentService


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


class EnvironmentGridBuilder:
    """Build point-sampled cells on a documented WGS84 grid contract.

    The first implementation is deliberately on-demand rather than a bulk
    raster generator. A future array builder can use the same cell contract.
    """

    grid_crs = "EPSG:4326"
    grid_kind = "regular_latitude_longitude"
    recommended_resolution = "0.03 degree (~3 km at 80N)"
    max_batch_points = 1000

    def __init__(self, environment_service: EnvironmentService, *, cache_size: int = 4096) -> None:
        if cache_size <= 0:
            raise ValueError("cache_size must be positive")
        self.environment_service = environment_service
        self._cache_size = cache_size
        self._cache: OrderedDict[tuple[float, float, datetime], EnvironmentCell] = OrderedDict()
        self._lock = RLock()

    def query(self, latitude: float, longitude: float, timestamp: datetime) -> EnvironmentCell:
        position = Position(latitude=latitude, longitude=longitude)
        requested = _utc(timestamp)
        key = (round(position.latitude, 6), round(position.longitude, 6), requested)
        with self._lock:
            cached = self._cache.pop(key, None)
            if cached is not None:
                self._cache[key] = cached
                return cached.model_copy(deep=True)

        state = self.environment_service.query_complete_environment(
            position.latitude, position.longitude, requested
        )
        cell = self._from_state(state, position, requested)
        with self._lock:
            self._cache.pop(key, None)
            self._cache[key] = cell.model_copy(deep=True)
            while len(self._cache) > self._cache_size:
                self._cache.popitem(last=False)
        return cell

    def query_many(
        self,
        points: list[tuple[str, Position]],
        timestamp: datetime,
    ) -> list[dict[str, object]]:
        if not points:
            raise ValueError("Environment grid points cannot be empty.")
        if len(points) > self.max_batch_points:
            raise ValueError(f"A maximum of {self.max_batch_points} environment grid points is supported.")
        requested = _utc(timestamp)
        return [
            {"id": point_id, "cell": self.query(position.latitude, position.longitude, requested)}
            for point_id, position in points
        ]

    def clear_cache(self) -> None:
        with self._lock:
            self._cache.clear()

    def metadata(self) -> dict[str, object]:
        return {
            "grid": self.grid_kind,
            "crs": self.grid_crs,
            "recommended_resolution": self.recommended_resolution,
            "spatial_mapping": {
                "bathymetry": "provider-native nearest-neighbour sample",
                "ice": "provider-native nearest-neighbour sample",
                "wind": "provider-native curvilinear nearest-neighbour sample",
                "current": "provider-native bilinear sample with grid-vector rotation",
                "wave": "provider-native bilinear scalar and circular-direction sample",
            },
            "time_resolution": "hourly request timeline; provider-native nearest match retained",
            "cache_size": self._cache_size,
        }

    @staticmethod
    def _from_state(state: EnvironmentState, position: Position, requested: datetime) -> EnvironmentCell:
        return EnvironmentCell(
            latitude=position.latitude,
            longitude=position.longitude,
            timestamp=requested,
            requested_time=requested,
            depth=state.depth,
            ice=state.ice,
            wind=state.wind,
            current=state.current,
            wave=state.wave,
            sources=state.sources,
        )
