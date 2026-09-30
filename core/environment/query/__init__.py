"""Stable, provider-neutral environment query contracts."""

from .enums import EnvironmentFieldType, EnvironmentScale
from .models import EnvironmentQueryRequest, EnvironmentSample, Position, TimeMatchInfo, TimeMatchStatus
from .scale import ScaleResolver
from .service import EnvironmentQueryService
from .spatial import GridCellIndex, SpatialResolver
from .temporal import TimeResolver

__all__ = [
    "EnvironmentFieldType",
    "EnvironmentQueryRequest",
    "EnvironmentSample",
    "EnvironmentScale",
    "GridCellIndex",
    "Position",
    "ScaleResolver",
    "EnvironmentQueryService",
    "SpatialResolver",
    "TimeMatchInfo",
    "TimeMatchStatus",
    "TimeResolver",
]
