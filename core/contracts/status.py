"""Statuses shared by data contracts and future feasibility checks."""

from enum import StrEnum


class FeasibilityStatus(StrEnum):
    """Three-valued feasibility result; it must be handled explicitly."""

    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"

    def __bool__(self) -> bool:
        raise TypeError("FeasibilityStatus cannot be used as a boolean; handle PASS, FAIL, and UNKNOWN explicitly")
