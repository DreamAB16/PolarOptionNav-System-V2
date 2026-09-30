"""Evidence attribution for parameters and future capability contracts."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class EvidenceStatus(StrEnum):
    STANDARD = "STANDARD"
    VESSEL_DATA = "VESSEL_DATA"
    LITERATURE = "LITERATURE"
    PROJECT_ASSUMPTION = "PROJECT_ASSUMPTION"
    CALIBRATED = "CALIBRATED"
    SYNTHETIC_MODEL = "SYNTHETIC_MODEL"
    UNKNOWN = "UNKNOWN"


class EvidenceRecord(BaseModel):
    """Reusable provenance record; confidence is not implicitly a probability."""

    model_config = ConfigDict(frozen=True)

    source: str | None = None
    status: EvidenceStatus
    applicability: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    notes: str | None = None


ParameterEvidence = EvidenceRecord
