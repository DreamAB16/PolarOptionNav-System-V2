"""WGS84 geographic to Foundation Local ENU coordinate conversion."""

from math import cos, radians, sin, sqrt

from pyproj import Transformer

from core.contracts import LocalENUFrameRef, LocalENUPosition, WGS84Position


_WGS84_SEMI_MAJOR_M = 6_378_137.0
_WGS84_FLATTENING = 1.0 / 298.257223563
_WGS84_ECCENTRICITY_SQUARED = _WGS84_FLATTENING * (2.0 - _WGS84_FLATTENING)
_ECEF_TO_WGS84 = Transformer.from_crs("EPSG:4978", "EPSG:4979", always_xy=True)


def _ecef(latitude_rad: float, longitude_rad: float) -> tuple[float, float, float]:
    sin_lat = sin(latitude_rad)
    cos_lat = cos(latitude_rad)
    prime_vertical_radius = _WGS84_SEMI_MAJOR_M / sqrt(
        1.0 - _WGS84_ECCENTRICITY_SQUARED * sin_lat * sin_lat
    )
    return (
        prime_vertical_radius * cos_lat * cos(longitude_rad),
        prime_vertical_radius * cos_lat * sin(longitude_rad),
        prime_vertical_radius * (1.0 - _WGS84_ECCENTRICITY_SQUARED) * sin_lat,
    )


def wgs84_to_local_enu(
    position: WGS84Position, frame: LocalENUFrameRef
) -> LocalENUPosition:
    """Convert a WGS84 surface point into the frame-origin tangent ENU axes.

    The Foundation frame reference is preserved on the result. Geodetic height
    is assumed to be zero for both the origin and input position.
    """

    origin_lat = radians(frame.origin_lat_deg)
    origin_lon = radians(frame.origin_lon_deg)
    point_lat = radians(position.latitude_deg)
    point_lon = radians(position.longitude_deg)
    origin_x, origin_y, origin_z = _ecef(origin_lat, origin_lon)
    point_x, point_y, point_z = _ecef(point_lat, point_lon)
    delta_x = point_x - origin_x
    delta_y = point_y - origin_y
    delta_z = point_z - origin_z

    east = -sin(origin_lon) * delta_x + cos(origin_lon) * delta_y
    north = (
        -sin(origin_lat) * cos(origin_lon) * delta_x
        - sin(origin_lat) * sin(origin_lon) * delta_y
        + cos(origin_lat) * delta_z
    )
    up = (
        cos(origin_lat) * cos(origin_lon) * delta_x
        + cos(origin_lat) * sin(origin_lon) * delta_y
        + sin(origin_lat) * delta_z
    )
    return LocalENUPosition(
        frame=frame,
        x_east_m=east,
        y_north_m=north,
        z_up_m=up,
    )


def local_enu_to_wgs84(position: LocalENUPosition) -> WGS84Position:
    """Convert a Foundation Local ENU point back to WGS84 latitude/longitude."""

    frame = position.frame
    origin_lat = radians(frame.origin_lat_deg)
    origin_lon = radians(frame.origin_lon_deg)
    origin_x, origin_y, origin_z = _ecef(origin_lat, origin_lon)
    east = position.x_east_m
    north = position.y_north_m
    up = position.z_up_m

    x = origin_x - sin(origin_lon) * east - sin(origin_lat) * cos(origin_lon) * north + cos(origin_lat) * cos(origin_lon) * up
    y = origin_y + cos(origin_lon) * east - sin(origin_lat) * sin(origin_lon) * north + cos(origin_lat) * sin(origin_lon) * up
    z = origin_z + cos(origin_lat) * north + sin(origin_lat) * up
    longitude, latitude, _ = _ECEF_TO_WGS84.transform(x, y, z)
    return WGS84Position(latitude_deg=latitude, longitude_deg=longitude)
