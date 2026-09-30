"""Environment field metadata composed from Foundation contracts."""

from pydantic import BaseModel, ConfigDict, Field

from core.contracts import EvidenceRecord, QualityMetadata, TimeMetadata
from core.contracts.quality import AvailabilityStatus


class FieldMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_id: str | None
    native_resolution_m: float | None = Field(default=None, gt=0)
    representation_resolution_m: float | None = Field(default=None, gt=0)
    time: TimeMetadata
    quality: QualityMetadata
    evidence: EvidenceRecord
    direction_convention: str | None = None

    @property
    def availability(self) -> AvailabilityStatus:
        """Expose availability through the Foundation quality contract."""

        return self.quality.availability


class EnvironmentSnapshotMetadata(BaseModel):
    """Optional descriptive metadata for a composed environment snapshot."""

    model_config = ConfigDict(frozen=True)

    snapshot_id: str | None = None
    version: str | None = None
