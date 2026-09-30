"""Static propulsion-system parameter contracts without performance logic."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PropulsionType(StrEnum):
    DIESEL = "DIESEL"
    DIESEL_ELECTRIC = "DIESEL_ELECTRIC"
    HYBRID = "HYBRID"
    NUCLEAR = "NUCLEAR"
    UNKNOWN = "UNKNOWN"


class PropulsionSystem(BaseModel):
    """Installed propulsion facts in SI-compatible units; no derived performance."""

    model_config = ConfigDict(frozen=True)

    propulsion_type: PropulsionType
    rated_power_kw: float | None = Field(default=None, ge=0)
    maximum_continuous_power_kw: float | None = Field(default=None, ge=0)
    minimum_operating_power_kw: float | None = Field(default=None, ge=0)
    propeller_efficiency: float | None = Field(default=None, gt=0, le=1)
    shaft_efficiency: float | None = Field(default=None, gt=0, le=1)
    number_of_propellers: int = Field(gt=0)

    @field_validator("propulsion_type", mode="before")
    @classmethod
    def require_propulsion_type_enum(cls, value: object) -> PropulsionType:
        if not isinstance(value, PropulsionType):
            raise ValueError("propulsion_type must be a PropulsionType member")
        return value


__all__ = ["PropulsionSystem", "PropulsionType"]
