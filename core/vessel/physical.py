"""Static vessel physical parameter contracts; no performance calculations."""

from pydantic import BaseModel, ConfigDict, Field


class HullGeometry(BaseModel):
    """Principal hull dimensions and block coefficient in SI units."""

    model_config = ConfigDict(frozen=True)

    length_overall_m: float | None = Field(default=None, gt=0)
    length_waterline_m: float | None = Field(default=None, gt=0)
    beam_m: float | None = Field(default=None, gt=0)
    draft_m: float | None = Field(default=None, gt=0)
    depth_m: float | None = Field(default=None, gt=0)
    block_coefficient: float | None = Field(default=None, gt=0, le=1)


class MassProperties(BaseModel):
    """Mass and displacement facts in tonnes."""

    model_config = ConfigDict(frozen=True)

    lightship_mass_t: float | None = Field(default=None, ge=0)
    deadweight_t: float | None = Field(default=None, ge=0)
    displacement_t: float | None = Field(default=None, ge=0)
    draft_condition: str | None = None


class HydrodynamicParameters(BaseModel):
    """Basic underwater geometry parameters; intentionally computation-free."""

    model_config = ConfigDict(frozen=True)

    wetted_surface_area_m2: float | None = Field(default=None, gt=0)
    reference_area_m2: float | None = Field(default=None, gt=0)
    underwater_volume_m3: float | None = Field(default=None, gt=0)


__all__ = ["HullGeometry", "MassProperties", "HydrodynamicParameters"]
