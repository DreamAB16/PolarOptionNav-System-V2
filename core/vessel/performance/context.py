"""Execution context contracts for future vessel performance models."""

from pydantic import BaseModel, ConfigDict, field_validator

from core.contracts import TimeMetadata, WGS84Position
from core.environment.query.models import EnvironmentSample
from core.vessel.models import VesselState


class PerformanceContext(BaseModel):
    """Unified vessel, position, time, and pre-resolved environment input."""

    model_config = ConfigDict(frozen=True)

    vessel_state: VesselState
    position: WGS84Position
    time: TimeMetadata
    environment: EnvironmentSample | None = None

    @field_validator("time")
    @classmethod
    def require_valid_time(cls, value: TimeMetadata) -> TimeMetadata:
        if value.valid_time is None:
            raise ValueError("Performance context time.valid_time is required")
        return value


__all__ = ["PerformanceContext"]
