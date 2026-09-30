"""Availability and quality metadata without policy thresholds."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class AvailabilityStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    AGING = "AGING"
    STALE = "STALE"
    MISSING = "MISSING"
    CONFLICT = "CONFLICT"
    INVALID = "INVALID"


class QualityMetadata(BaseModel):
    """Source quality annotation; interpretation is left to later policy layers."""

    model_config = ConfigDict(frozen=True)

    availability: AvailabilityStatus
    uncertainty: float | None = Field(default=None, ge=0)
    source: str | None = None
    reason: str | None = None
