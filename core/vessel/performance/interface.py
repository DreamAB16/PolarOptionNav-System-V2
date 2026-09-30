"""Protocol for future vessel performance models."""

from typing import Protocol, runtime_checkable

from .models import PerformanceInput, VesselPerformanceState


@runtime_checkable
class VesselPerformanceModel(Protocol):
    """Contract implemented later by concrete performance models."""

    def evaluate(self, input: PerformanceInput) -> VesselPerformanceState:
        """Return one performance state without route, ETA, risk, or feasibility logic."""


__all__ = ["VesselPerformanceModel"]
