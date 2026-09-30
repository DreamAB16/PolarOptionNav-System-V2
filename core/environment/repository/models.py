"""Keys used to index environment snapshots."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from core.contracts import ensure_utc
from core.environment.enums import EnvironmentScale


class EnvironmentSnapshotKey(BaseModel):
    model_config = ConfigDict(frozen=True)

    scale: EnvironmentScale
    valid_time: datetime

    @field_validator("valid_time")
    @classmethod
    def normalize_valid_time(cls, value: datetime) -> datetime:
        return ensure_utc(value)


__all__ = ["EnvironmentSnapshotKey"]
