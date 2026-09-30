"""Shared environment scale and field-kind identifiers."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EnvironmentScale(StrEnum):
    NEAR = "near"
    MIDDLE = "middle"
    REMOTE = "remote"


class EnvironmentVariable(StrEnum):
    BATHYMETRY = "bathymetry"
    WIND = "wind"
    CURRENT = "current"
    ICE = "ice"
    WAVE = "wave"


class EnvironmentScaleSpec(BaseModel):
    """Nominal spatial and refresh targets for one environment scale."""

    model_config = ConfigDict(frozen=True)

    scale: EnvironmentScale
    range_min_nm: float = Field(ge=0)
    range_max_nm: float = Field(gt=0)
    representation_resolution_m: float = Field(gt=0)
    refresh_min_s: float = Field(gt=0)
    refresh_max_s: float = Field(gt=0)

    @model_validator(mode="after")
    def validate_ranges(self) -> "EnvironmentScaleSpec":
        if self.range_max_nm <= self.range_min_nm:
            raise ValueError("Scale range must have positive width.")
        if self.refresh_max_s < self.refresh_min_s:
            raise ValueError("Refresh maximum must not be less than refresh minimum.")
        return self


ENVIRONMENT_SCALE_SPECS = {
    EnvironmentScale.NEAR: EnvironmentScaleSpec(
        scale=EnvironmentScale.NEAR,
        range_min_nm=0,
        range_max_nm=3,
        representation_resolution_m=75,
        refresh_min_s=1,
        refresh_max_s=5,
    ),
    EnvironmentScale.MIDDLE: EnvironmentScaleSpec(
        scale=EnvironmentScale.MIDDLE,
        range_min_nm=2,
        range_max_nm=15,
        representation_resolution_m=250,
        refresh_min_s=300,
        refresh_max_s=600,
    ),
    EnvironmentScale.REMOTE: EnvironmentScaleSpec(
        scale=EnvironmentScale.REMOTE,
        range_min_nm=12,
        range_max_nm=50,
        representation_resolution_m=1000,
        refresh_min_s=1800,
        refresh_max_s=3600,
    ),
}
