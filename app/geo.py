from __future__ import annotations

from math import asin, cos, radians, sin, sqrt


def distance_meters(
    origin_latitude: float,
    origin_longitude: float,
    destination_latitude: float,
    destination_longitude: float,
) -> float:
    """Return the great-circle distance between two WGS84 coordinates."""
    earth_radius_meters = 6_371_000
    lat_delta = radians(destination_latitude - origin_latitude)
    lon_delta = radians(destination_longitude - origin_longitude)
    origin_lat = radians(origin_latitude)
    destination_lat = radians(destination_latitude)
    value = (
        sin(lat_delta / 2) ** 2
        + cos(origin_lat) * cos(destination_lat) * sin(lon_delta / 2) ** 2
    )
    return earth_radius_meters * 2 * asin(sqrt(value))
