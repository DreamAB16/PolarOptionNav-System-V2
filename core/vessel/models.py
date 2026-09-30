"""Provider-neutral vessel capability and state contracts."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from core.contracts import WGS84Position, ensure_utc

from .enums import IceClass


class VesselCapability(BaseModel):
    """Static vessel facts expressed in SI units."""

    model_config = ConfigDict(frozen=True)

    vessel_id: str = Field(min_length=1)
    length_m: float | None = Field(default=None, gt=0)
    beam_m: float | None = Field(default=None, gt=0)
    draft_m: float | None = Field(default=None, gt=0)
    displacement_t: float | None = Field(default=None, gt=0)
    propulsion_power_kw: float | None = Field(default=None, gt=0)
    ice_class: IceClass

    @field_validator("ice_class", mode="before")
    @classmethod
    def require_ice_class_enum(cls, value: object) -> IceClass:
        if not isinstance(value, IceClass):
            raise ValueError("ice_class must be an IceClass member")
        return value


class VesselState(BaseModel):
    """Current vessel facts; no performance, risk, or feasibility interpretation."""

    model_config = ConfigDict(frozen=True)

    position: WGS84Position
    heading: float | None = None
    speed_mps: float | None = Field(default=None, ge=0)
    power_fraction: float | None = Field(default=None, ge=0, le=1)
    draft_m: float | None = Field(default=None, gt=0)
    timestamp: datetime

    @field_validator("timestamp")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        return ensure_utc(value)


class VesselIdentity(BaseModel):
    id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    vessel_type: str = Field(..., min_length=1)
    operator: str | None = None


class VesselGeometry(BaseModel):
    length_m: float = Field(..., gt=0)
    beam_m: float = Field(..., gt=0)
    design_draft_m: float = Field(..., gt=0)


class VesselMass(BaseModel):
    design_displacement_t: float = Field(..., gt=0)


class VesselPropulsion(BaseModel):
    type: str = Field(..., min_length=1)
    azipod_count: int = Field(..., ge=0)
    azipod_power_mw_each: float = Field(..., gt=0)
    total_propulsion_power_mw: float = Field(..., gt=0)


class VesselSpeed(BaseModel):
    service_speed_min_kn: float = Field(..., ge=0)
    service_speed_max_kn: float = Field(..., ge=0)
    maximum_speed_kn: float = Field(..., ge=0)
    endurance_nmi: float = Field(..., gt=0)
    endurance_days: int = Field(..., gt=0)


class IceCapability(BaseModel):
    ice_class: str = Field(..., min_length=1)
    continuous_ice_thickness_m: float = Field(..., ge=0)
    continuous_snow_thickness_m: float = Field(..., ge=0)
    continuous_ice_speed_min_kn: float = Field(..., ge=0)
    continuous_ice_speed_max_kn: float = Field(..., ge=0)


class VesselSafetyConstraints(BaseModel):
    draft: float = Field(..., gt=0)
    ice_class: str = Field(..., min_length=1)
    power: float = Field(..., gt=0)
    speed_limit: float = Field(..., gt=0)


class VesselSource(BaseModel):
    title: str
    url: str
    fields: list[str] = Field(default_factory=list)


class VesselProfile(BaseModel):
    identity: VesselIdentity
    geometry: VesselGeometry
    mass: VesselMass
    propulsion: VesselPropulsion
    speed: VesselSpeed
    ice_capability: IceCapability
    safety_constraints: VesselSafetyConstraints
    sources: list[VesselSource] = Field(default_factory=list)


__all__ = [
    "IceCapability",
    "VesselCapability",
    "VesselGeometry",
    "VesselIdentity",
    "VesselMass",
    "VesselProfile",
    "VesselPropulsion",
    "VesselSafetyConstraints",
    "VesselSource",
    "VesselSpeed",
    "VesselState",
]
