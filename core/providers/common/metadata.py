"""Build environment field metadata from existing shared contracts."""

from core.contracts import EvidenceRecord, QualityMetadata, TimeMetadata
from core.environment import FieldMetadata


def build_field_metadata(
    *,
    source_id: str | None,
    native_resolution_m: float | None,
    representation_resolution_m: float | None,
    time: TimeMetadata,
    quality: QualityMetadata,
    evidence: EvidenceRecord,
) -> FieldMetadata:
    """Construct the Environment Contract metadata without parallel DTOs."""

    return FieldMetadata(
        source_id=source_id,
        native_resolution_m=native_resolution_m,
        representation_resolution_m=representation_resolution_m,
        time=time,
        quality=quality,
        evidence=evidence,
    )
