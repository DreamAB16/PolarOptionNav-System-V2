from math import pi

import pytest

from core.contracts.directions import (
    CurrentDirectionTo,
    WaveDirectionFrom,
    WindDirectionFrom,
    from_bearing_speed_to_en,
    from_bearing_to_to_bearing,
    to_bearing_speed_to_en,
)


@pytest.mark.parametrize(
    "bearing_deg, expected",
    [(0, (0, 1)), (90, (1, 0)), (180, (0, -1)), (270, (-1, 0))],
)
def test_to_bearing_cardinals(bearing_deg: float, expected: tuple[float, float]) -> None:
    assert to_bearing_speed_to_en(1, pi * bearing_deg / 180) == pytest.approx(expected)


def test_from_bearing_is_explicitly_reversed_before_vector_conversion() -> None:
    assert from_bearing_to_to_bearing(0) == pytest.approx(pi)
    assert from_bearing_speed_to_en(1, 0) == pytest.approx((0, -1))


def test_wave_from_uses_the_same_explicit_physical_vector_semantics_as_wind() -> None:
    assert from_bearing_speed_to_en(1, pi / 2) == pytest.approx((-1, 0))


def test_direction_wrappers_keep_from_to_semantics_in_names() -> None:
    assert WindDirectionFrom(0).navigation_bearing_rad == 0
    assert WaveDirectionFrom(pi).navigation_bearing_rad == pi
    assert CurrentDirectionTo(pi / 2).navigation_bearing_rad == pi / 2
