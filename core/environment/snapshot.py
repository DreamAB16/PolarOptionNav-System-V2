"""Scale snapshots and the complete multi-scale environment state."""

from pydantic import BaseModel, ConfigDict, model_validator

from core.contracts import TimeMetadata

from .enums import EnvironmentScale, EnvironmentVariable
from .fields import EnvironmentField
from .grid import GridSpec
from .metadata import EnvironmentSnapshotMetadata


class EnvironmentScaleSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    scale: EnvironmentScale
    grid: GridSpec
    fields: dict[EnvironmentVariable, EnvironmentField]
    metadata: EnvironmentSnapshotMetadata
    time_context: TimeMetadata

    @model_validator(mode="after")
    def validate_fields(self) -> "EnvironmentScaleSnapshot":
        for key, field in self.fields.items():
            if key != field.variable:
                raise ValueError("Field mapping key must match the field variable.")
        return self


class MultiScaleEnvironmentState(BaseModel):
    model_config = ConfigDict(frozen=True)

    near: EnvironmentScaleSnapshot
    middle: EnvironmentScaleSnapshot
    remote: EnvironmentScaleSnapshot

    @model_validator(mode="after")
    def validate_scale_members(self) -> "MultiScaleEnvironmentState":
        expected = (
            (self.near, EnvironmentScale.NEAR),
            (self.middle, EnvironmentScale.MIDDLE),
            (self.remote, EnvironmentScale.REMOTE),
        )
        if any(snapshot.scale != scale for snapshot, scale in expected):
            raise ValueError("Each multi-scale member must carry its corresponding scale.")
        return self


__all__ = ["EnvironmentScaleSnapshot", "MultiScaleEnvironmentState"]
