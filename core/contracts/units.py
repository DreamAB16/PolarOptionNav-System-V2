"""Pure, explicit conversions at API and display boundaries."""

from math import pi


NAUTICAL_MILE_METRES = 1852.0
KNOT_METRES_PER_SECOND = 1852.0 / 3600.0


def nautical_miles_to_metres(value: float) -> float:
    return value * NAUTICAL_MILE_METRES


def metres_to_nautical_miles(value: float) -> float:
    return value / NAUTICAL_MILE_METRES


def knots_to_metres_per_second(value: float) -> float:
    return value * KNOT_METRES_PER_SECOND


def metres_per_second_to_knots(value: float) -> float:
    return value / KNOT_METRES_PER_SECOND


def degrees_to_radians(value: float) -> float:
    return value * pi / 180.0


def radians_to_degrees(value: float) -> float:
    return value * 180.0 / pi
