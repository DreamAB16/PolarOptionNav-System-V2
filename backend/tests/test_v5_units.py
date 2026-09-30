import pytest

from core.contracts.units import (
    degrees_to_radians,
    knots_to_metres_per_second,
    metres_per_second_to_knots,
    metres_to_nautical_miles,
    nautical_miles_to_metres,
    radians_to_degrees,
)


def test_nautical_mile_conversion() -> None:
    assert nautical_miles_to_metres(1) == pytest.approx(1852)
    assert nautical_miles_to_metres(10) == pytest.approx(18520)
    assert metres_to_nautical_miles(18520) == pytest.approx(10)


@pytest.mark.parametrize("knots", [1, 2, 5, 8, 12])
def test_knots_round_trip(knots: float) -> None:
    assert knots_to_metres_per_second(knots) == pytest.approx(knots * 1852 / 3600)
    assert metres_per_second_to_knots(knots_to_metres_per_second(knots)) == pytest.approx(knots)


@pytest.mark.parametrize("degrees", [0, 90, 180, 270, 360])
def test_degree_radian_round_trip(degrees: float) -> None:
    assert radians_to_degrees(degrees_to_radians(degrees)) == pytest.approx(degrees)
