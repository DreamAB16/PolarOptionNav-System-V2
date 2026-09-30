"""Point-in-time environment query result contract."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from core.contracts import LocalENUPosition, ensure_utc

from .enums import EnvironmentVariable
from .metadata import FieldMetadata


class EnvironmentSample(BaseModel):
    """One variable value (or explicit unknown) at an ENU position and UTC time."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    position: LocalENUPosition
    time: datetime
    variable: EnvironmentVariable
    value: object | None
    metadata: FieldMetadata

    @field_validator("time")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return ensure_utc(value)
