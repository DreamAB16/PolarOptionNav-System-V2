from math import pi

import pytest

from core.contracts.coordinates import (
    LocalENUFrameRef,
    LocalENUPosition,
    WGS84Position,
    bearing_to_math_yaw,
    math_yaw_to_bearing,
    wrap_2pi,
    wrap_pi,
)


@pytest.mark.parametrize("bearing_deg, yaw_deg", [(0, 90), (90, 0), (180, 270), (270, 180)])
def test_cardinal_bearing_to_math_yaw(bearing_deg: float, yaw_deg: float) -> None:
    assert bearing_to_math_yaw(pi * bearing_deg / 180) == pytest.approx(pi * yaw_deg / 180)


@pytest.mark.parametrize("bearing_deg", [0, 1, 359, -1, 360, 721, -721])
def test_bearing_yaw_round_trip_and_wrapping(bearing_deg: float) -> None:
    bearing = pi * bearing_deg / 180
    assert math_yaw_to_bearing(bearing_to_math_yaw(bearing)) == pytest.approx(wrap_2pi(bearing))


def test_angle_wrapping_conventions() -> None:
    assert wrap_2pi(2 * pi) == pytest.approx(0)
    assert wrap_2pi(-pi / 2) == pytest.approx(3 * pi / 2)
    assert wrap_pi(3 * pi / 2) == pytest.approx(-pi / 2)
    assert wrap_pi(-pi) == pytest.approx(-pi)


def test_local_enu_frame_reference_validates_wgs84_origin() -> None:
    frame = LocalENUFrameRef(
        frame_id="barents-01",
        origin_lat_deg=78.2,
        origin_lon_deg=15.6,
        crs_or_projection_identifier="EPSG:32633",
    )
    assert frame.origin_lat_deg == 78.2
    with pytest.raises(ValueError):
        LocalENUFrameRef(frame_id="bad", origin_lat_deg=91, origin_lon_deg=0, crs_or_projection_identifier="x")


def test_wgs84_boundary_position_and_local_enu_position_are_distinct() -> None:
    frame = LocalENUFrameRef(frame_id="barents-01", origin_lat_deg=78.2, origin_lon_deg=15.6, crs_or_projection_identifier="EPSG:32633")
    assert WGS84Position(latitude_deg=78.2, longitude_deg=15.6).latitude_deg == 78.2
    position = LocalENUPosition(frame=frame, x_east_m=125.0, y_north_m=-80.0)
    assert (position.x_east_m, position.y_north_m, position.z_up_m) == (125.0, -80.0, 0.0)
