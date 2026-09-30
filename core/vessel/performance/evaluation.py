"""Contracts and registry for vessel performance evaluation."""

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from core.contracts import EvidenceRecord, QualityMetadata, TimeMetadata

from .context import PerformanceContext
from .enums import PerformanceMetric


class PerformanceRequest(BaseModel):
    """One evaluation request against a pre-resolved performance context."""

    model_config = ConfigDict(frozen=True)

    context: PerformanceContext
    requested_metrics: list[PerformanceMetric] = Field(min_length=1)
    timestamp: TimeMetadata


class PerformanceResult(BaseModel):
    """Evaluator output; ``None`` means unknown and is never represented by zero."""

    model_config = ConfigDict(frozen=True)

    speed_mps: float | None = Field(default=None, ge=0)
    power_required_kw: float | None = Field(default=None, ge=0)
    energy_rate_kw: float | None = Field(default=None, ge=0)
    ice_capability: object | None = None
    quality: QualityMetadata
    evidence: EvidenceRecord
    time: TimeMetadata


@runtime_checkable
class PerformanceEvaluator(Protocol):
    """Contract implemented by replaceable performance models."""

    def evaluate(self, request: PerformanceRequest) -> PerformanceResult:
        """Return one performance result without route, ETA, risk, or feasibility logic."""


class PerformanceModelRegistry:
    """Small in-memory registry for evaluator implementations."""

    def __init__(self) -> None:
        self._evaluators: dict[str, PerformanceEvaluator] = {}

    def register(self, model_id: str, evaluator: PerformanceEvaluator) -> None:
        """Register one evaluator under an explicit, stable identifier."""

        normalized_id = model_id.strip()
        if not normalized_id:
            raise ValueError("Performance model id must not be empty")
        if not isinstance(evaluator, PerformanceEvaluator):
            raise TypeError("Performance model must implement PerformanceEvaluator")
        if normalized_id in self._evaluators:
            raise ValueError(f"Performance model id is already registered: {normalized_id}")
        self._evaluators[normalized_id] = evaluator

    def get(self, model_id: str) -> PerformanceEvaluator | None:
        """Return a registered evaluator or ``None`` when the id is unknown."""

        return self._evaluators.get(model_id)

    def model_ids(self) -> tuple[str, ...]:
        """Return registered ids in insertion order."""

        return tuple(self._evaluators)


__all__ = [
    "PerformanceEvaluator",
    "PerformanceModelRegistry",
    "PerformanceRequest",
    "PerformanceResult",
]
