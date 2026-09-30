"""Contracts for requesting and representing point environment queries."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from core.contracts import (
    AvailabilityStatus,
    LocalENUPosition,
    QualityMetadata,
    TimeMetadata,
    WGS84Position,
    ensure_utc,
)
from core.environment.fields import EnvironmentField

from .enums import EnvironmentFieldType, EnvironmentScale


class TimeMatchStatus(StrEnum):
    EXACT = "EXACT"
    NEAREST = "NEAREST"
    UNAVAILABLE = "UNAVAILABLE"


class TimeMatchInfo(BaseModel):
    model_config = ConfigDict(frozen=True)

    requested_time: datetime
    matched_time: datetime | None = None
    offset_seconds: float | None = None
    status: TimeMatchStatus

    @field_validator("requested_time", "matched_time")
    @classmethod
    def normalize_times(cls, value: datetime | None) -> datetime | None:
        return None if value is None else ensure_utc(value)


class EnvironmentQueryRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    position: WGS84Position
    target_time: datetime
    scale: EnvironmentScale
    requested_fields: list[EnvironmentFieldType] = Field(min_length=1)

    @field_validator("target_time")
    @classmethod
    def normalize_target_time(cls, value: datetime) -> datetime:
        return ensure_utc(value)


class EnvironmentSample(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    position: LocalENUPosition
    requested_time: datetime
    matched_time: datetime | None = None
    fields: dict[EnvironmentFieldType, EnvironmentField | None]
    quality: QualityMetadata
    availability: AvailabilityStatus
    time_match: TimeMatchInfo

    @field_validator("requested_time", "matched_time")
    @classmethod
    def normalize_times(cls, value: datetime | None) -> datetime | None:
        return None if value is None else ensure_utc(value)


# Foundation Position is geographic WGS84; this alias makes the query API name explicit.
Position = WGS84Position

__all__ = [
    "EnvironmentQueryRequest",
    "EnvironmentSample",
    "Position",
    "TimeMatchInfo",
    "TimeMatchStatus",
]
