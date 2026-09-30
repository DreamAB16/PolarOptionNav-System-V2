"""Input and output contracts for future vessel performance models."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from core.contracts import EvidenceRecord, QualityMetadata, TimeMetadata
from core.vessel.models import VesselCapability, VesselState
from core.vessel.physical import HullGeometry, HydrodynamicParameters, MassProperties
from core.vessel.propulsion import PropulsionSystem


class VesselPhysicalModel(BaseModel):
    """Aggregate view of the existing physical contracts; adds no new physics."""

    model_config = ConfigDict(frozen=True)

    geometry: HullGeometry
    mass: MassProperties
    hydrodynamics: HydrodynamicParameters


class PerformanceInput(BaseModel):
    """Describe the inputs a future performance model may consume.

    ``environment_context`` is intentionally opaque.  This phase does not bind
    performance to an environment implementation or permit it to read providers.
    """

    model_config = ConfigDict(frozen=True)

    vessel_capability: VesselCapability
    vessel_state: VesselState
    physical_model: VesselPhysicalModel
    propulsion_system: PropulsionSystem
    environment_context: object | None = None


class VesselPerformanceState(BaseModel):
    """Performance state values; ``None`` means unknown, never zero."""

    model_config = ConfigDict(frozen=True)

    available_power_kw: float | None = Field(default=None, ge=0)
    operating_power_kw: float | None = Field(default=None, ge=0)
    effective_power_kw: float | None = Field(default=None, ge=0)
    propulsion_efficiency: float | None = Field(default=None, ge=0, le=1)
    quality: QualityMetadata
    evidence: EvidenceRecord
    timestamp: TimeMetadata

    @field_validator("timestamp")
    @classmethod
    def require_valid_time(cls, value: TimeMetadata) -> TimeMetadata:
        if value.valid_time is None:
            raise ValueError("Performance state timestamp.valid_time is required")
        return value


__all__ = [
    "PerformanceInput",
    "VesselPerformanceState",
    "VesselPhysicalModel",
]
