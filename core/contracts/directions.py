"""Direction-from/to contracts and east/north vector helpers."""

from dataclasses import dataclass
from math import cos, sin

from .coordinates import wrap_2pi


@dataclass(frozen=True)
class WindDirectionFrom:
    navigation_bearing_rad: float


@dataclass(frozen=True)
class WaveDirectionFrom:
    navigation_bearing_rad: float


@dataclass(frozen=True)
class CurrentDirectionTo:
    navigation_bearing_rad: float


def from_bearing_to_to_bearing(from_bearing_rad: float) -> float:
    """Reverse a direction explicitly: origin bearing to destination bearing."""

    return wrap_2pi(from_bearing_rad + 3.141592653589793)


def to_bearing_speed_to_en(speed_mps: float, bearing_to_rad: float) -> tuple[float, float]:
    """Convert a destination bearing and speed to ``(east, north)`` m/s."""

    return speed_mps * sin(bearing_to_rad), speed_mps * cos(bearing_to_rad)


def from_bearing_speed_to_en(speed_mps: float, bearing_from_rad: float) -> tuple[float, float]:
    """Convert a source bearing and speed via an explicit FROM -> TO step."""

    return to_bearing_speed_to_en(speed_mps, from_bearing_to_to_bearing(bearing_from_rad))
