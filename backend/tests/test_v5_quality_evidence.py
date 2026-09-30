import pytest

from core.contracts.evidence import EvidenceRecord, EvidenceStatus
from core.contracts.quality import AvailabilityStatus, QualityMetadata
from core.contracts.status import FeasibilityStatus


def test_availability_statuses_are_explicit() -> None:
    assert {item.value for item in AvailabilityStatus} == {
        "AVAILABLE", "AGING", "STALE", "MISSING", "CONFLICT", "INVALID"
    }
    assert QualityMetadata(availability=AvailabilityStatus.MISSING).uncertainty is None


def test_evidence_statuses_include_synthetic_model() -> None:
    assert EvidenceStatus.SYNTHETIC_MODEL.value == "SYNTHETIC_MODEL"
    record = EvidenceRecord(
        source="test fixture",
        status=EvidenceStatus.SYNTHETIC_MODEL,
        applicability="local manoeuvre fixture",
        confidence=0.5,
        notes="Confidence is an attribution field, not a probability claim.",
    )
    assert record.status is EvidenceStatus.SYNTHETIC_MODEL


def test_evidence_confidence_is_structurally_bounded_when_present() -> None:
    with pytest.raises(ValueError):
        EvidenceRecord(status=EvidenceStatus.UNKNOWN, confidence=1.1)


def test_feasibility_is_explicit_three_state_and_unknown_cannot_be_treated_as_safe() -> None:
    assert {item.value for item in FeasibilityStatus} == {"PASS", "FAIL", "UNKNOWN"}
    with pytest.raises(TypeError, match="cannot be used as a boolean"):
        bool(FeasibilityStatus.UNKNOWN)
