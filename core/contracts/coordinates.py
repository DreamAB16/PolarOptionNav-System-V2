"""Explicit WGS84, local ENU, bearing, and mathematical-yaw semantics."""

from math import pi

from pydantic import BaseModel, ConfigDict, Field


def wrap_2pi(angle_rad: float) -> float:
    """Return an angle in the half-open interval ``[0, 2*pi)``."""

    return angle_rad % (2.0 * pi)


def wrap_pi(angle_rad: float) -> float:
    """Return an angle in the half-open interval ``[-pi, pi)``."""

    return (angle_rad + pi) % (2.0 * pi) - pi


def bearing_to_math_yaw(navigation_bearing_rad: float) -> float:
    """Convert true-north clockwise bearing to east-zero CCW mathematical yaw."""

    return wrap_2pi(pi / 2.0 - navigation_bearing_rad)


def math_yaw_to_bearing(math_yaw_rad: float) -> float:
    """Convert east-zero CCW mathematical yaw to true-north clockwise bearing."""

    return wrap_2pi(pi / 2.0 - math_yaw_rad)


class LocalENUFrameRef(BaseModel):
    """Identity of a local East-North-Up metric frame."""

    model_config = ConfigDict(frozen=True)

    frame_id: str = Field(min_length=1)
    origin_lat_deg: float = Field(ge=-90.0, le=90.0)
    origin_lon_deg: float = Field(ge=-180.0, le=180.0)
    crs_or_projection_identifier: str = Field(min_length=1)


LocalFrame = LocalENUFrameRef


class WGS84Position(BaseModel):
    """Geographic boundary position in WGS84 decimal degrees, never an ENU point."""

    model_config = ConfigDict(frozen=True)

    latitude_deg: float = Field(ge=-90.0, le=90.0)
    longitude_deg: float = Field(ge=-180.0, le=180.0)


class LocalENUPosition(BaseModel):
    """Algorithm-space position in a named ENU frame; all coordinates are metres."""

    model_config = ConfigDict(frozen=True)

    frame: LocalENUFrameRef
    x_east_m: float
    y_north_m: float
    z_up_m: float = 0.0
