"""Static, replaceable land/obstacle mask for planning and viewport grids."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import math
from typing import Protocol

from services.environment_service.service import EnvironmentService

CELL_SIZE_KM = 25.0
LAND_OBSTACLE_THRESHOLD = 0.05


@dataclass(frozen=True, slots=True)
class LandMaskResult:
    is_land: bool
    land_ratio: float
    source: str


class LandMaskProvider(Protocol):
    """Provider boundary for GEBCO today and ENC polygons in the future."""

    def check_cell(self, latitude: float, longitude: float, cell_size_km: float = CELL_SIZE_KM) -> LandMaskResult: ...


class GebcoLandMaskProvider:
    """Classify 25 km cells from cached GEBCO zero-depth samples.

    The local chart GeoPackage only contains coastline lines.  GEBCO provides
    the actual static land/sea classification used by the planner, so it is
    the safe common source until an ENC polygon provider is installed.
    """

    source_name = "GEBCO_2026_sub_ice_land_mask"

    def __init__(self, environment_service: EnvironmentService, threshold: float = LAND_OBSTACLE_THRESHOLD):
        self.environment_service = environment_service
        self.threshold = threshold

    @lru_cache(maxsize=131_072)
    def _is_land_point(self, latitude: float, longitude: float) -> bool:
        try:
            return self.environment_service.query_bathymetry(latitude, longitude).depth <= 0.0
        except (LookupError, OSError, RuntimeError, ValueError, FileNotFoundError):
            # Unknown bathymetry is not silently called land. The planner's
            # separate depth hard constraint handles that case conservatively.
            return False

    def check_cell(self, latitude: float, longitude: float, cell_size_km: float = CELL_SIZE_KM) -> LandMaskResult:
        half_lat = cell_size_km / (2.0 * 111.32)
        cos_lat = max(0.03, math.cos(math.radians(latitude)))
        half_lon = cell_size_km / (2.0 * 111.32 * cos_lat)
        samples = (
            (latitude, longitude),
            (latitude - half_lat, longitude - half_lon),
            (latitude - half_lat, longitude + half_lon),
            (latitude + half_lat, longitude - half_lon),
            (latitude + half_lat, longitude + half_lon),
        )
        land_count = sum(self._is_land_point(round(lat, 6), round(lon, 6)) for lat, lon in samples)
        ratio = land_count / len(samples)
        return LandMaskResult(is_land=ratio >= self.threshold, land_ratio=ratio, source=self.source_name)


__all__ = ["CELL_SIZE_KM", "LAND_OBSTACLE_THRESHOLD", "LandMaskProvider", "LandMaskResult", "GebcoLandMaskProvider"]
