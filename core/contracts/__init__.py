"""V5 foundation contracts shared by future WEB services."""

from .coordinates import (
    LocalFrame,
    LocalENUFrameRef,
    LocalENUPosition,
    WGS84Position,
    bearing_to_math_yaw,
    math_yaw_to_bearing,
    wrap_2pi,
    wrap_pi,
)
from .directions import (
    CurrentDirectionTo,
    WaveDirectionFrom,
    WindDirectionFrom,
    from_bearing_to_to_bearing,
    from_bearing_speed_to_en,
    to_bearing_speed_to_en,
)
from .evidence import EvidenceRecord, EvidenceStatus, ParameterEvidence
from .quality import AvailabilityStatus, QualityMetadata
from .status import FeasibilityStatus
from .time import TimeMetadata, available_at_decision_time, data_age, ensure_utc, lead_time, staleness
from .units import (
    degrees_to_radians,
    knots_to_metres_per_second,
    metres_per_second_to_knots,
    metres_to_nautical_miles,
    nautical_miles_to_metres,
    radians_to_degrees,
)

V5_CONTRACT_VERSION = "5.0"
Availability = AvailabilityStatus

__all__ = [
    "AvailabilityStatus",
    "Availability",
    "CurrentDirectionTo",
    "EvidenceRecord",
    "EvidenceStatus",
    "LocalENUFrameRef",
    "LocalENUPosition",
    "LocalFrame",
    "ParameterEvidence",
    "QualityMetadata",
    "FeasibilityStatus",
    "TimeMetadata",
    "WGS84Position",
    "V5_CONTRACT_VERSION",
    "WaveDirectionFrom",
    "WindDirectionFrom",
    "bearing_to_math_yaw",
    "available_at_decision_time",
    "data_age",
    "degrees_to_radians",
    "ensure_utc",
    "from_bearing_speed_to_en",
    "from_bearing_to_to_bearing",
    "knots_to_metres_per_second",
    "lead_time",
    "math_yaw_to_bearing",
    "metres_per_second_to_knots",
    "metres_to_nautical_miles",
    "nautical_miles_to_metres",
    "radians_to_degrees",
    "staleness",
    "to_bearing_speed_to_en",
    "wrap_2pi",
    "wrap_pi",
]
