"""Contract-level identifiers for vessel performance outputs."""

from enum import StrEnum


class PerformanceOutputField(StrEnum):
    """Names of the values carried by ``VesselPerformanceState``."""

    AVAILABLE_POWER_KW = "available_power_kw"
    OPERATING_POWER_KW = "operating_power_kw"
    EFFECTIVE_POWER_KW = "effective_power_kw"
    PROPULSION_EFFICIENCY = "propulsion_efficiency"


__all__ = ["PerformanceOutputField"]


class PerformanceMetric(StrEnum):
    """Metric types that may be requested from a performance evaluator."""

    SPEED_CAPABILITY = "SPEED_CAPABILITY"
    POWER_REQUIREMENT = "POWER_REQUIREMENT"
    ENERGY_ESTIMATE = "ENERGY_ESTIMATE"
    ICE_CAPABILITY = "ICE_CAPABILITY"
    CONFIDENCE = "CONFIDENCE"


__all__ = ["PerformanceMetric", "PerformanceOutputField"]
