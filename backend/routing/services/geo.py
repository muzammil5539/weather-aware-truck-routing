"""Geometry helpers: distance along a polyline and checkpoint sampling.

Coordinates are (latitude, longitude) pairs in degrees throughout.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt

EARTH_RADIUS_MILES = 3958.7613
METERS_PER_MILE = 1609.344


def haversine_miles(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = radians(a[0]), radians(a[1])
    lat2, lon2 = radians(b[0]), radians(b[1])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * asin(sqrt(min(1.0, h)))


def cumulative_miles(points: list[tuple[float, float]]) -> list[float]:
    """Distance from the start of the polyline to each vertex."""
    out = [0.0]
    for prev, cur in zip(points, points[1:]):
        out.append(out[-1] + haversine_miles(prev, cur))
    return out


def _interpolate(a: tuple[float, float], b: tuple[float, float], t: float) -> tuple[float, float]:
    # Linear in lat/lon. Over a sub-segment of a road polyline (well under a
    # mile) the great-circle error is far below the resolution of a weather
    # forecast grid cell, so the simple form is the right one here.
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def point_at_distance(
    points: list[tuple[float, float]], cumulative: list[float], target_miles: float
) -> tuple[float, float]:
    """The point `target_miles` along the polyline, interpolating within a segment."""
    if target_miles <= 0:
        return points[0]
    if target_miles >= cumulative[-1]:
        return points[-1]
    lo, hi = 0, len(cumulative) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if cumulative[mid] < target_miles:
            lo = mid + 1
        else:
            hi = mid
    i = max(1, lo)
    span = cumulative[i] - cumulative[i - 1]
    t = 0.0 if span <= 0 else (target_miles - cumulative[i - 1]) / span
    return _interpolate(points[i - 1], points[i], t)


@dataclass(frozen=True)
class SampledPoint:
    index: int
    lat: float
    lon: float
    distance_miles: float  # from the route origin


def sample_every(
    points: list[tuple[float, float]], interval_miles: float, *, include_end: bool = True
) -> list[SampledPoint]:
    """Sample the polyline at a fixed spacing, always including the origin.

    The final checkpoint is the true destination rather than a point at a round
    multiple of the interval, so a route's last checkpoint is always the place
    the driver actually arrives.
    """
    if not points:
        return []
    if interval_miles <= 0:
        raise ValueError("interval_miles must be positive")

    cumulative = cumulative_miles(points)
    total = cumulative[-1]
    samples: list[SampledPoint] = []
    distance = 0.0
    index = 0
    while distance < total:
        lat, lon = point_at_distance(points, cumulative, distance)
        samples.append(SampledPoint(index=index, lat=lat, lon=lon, distance_miles=distance))
        index += 1
        distance += interval_miles

    if include_end:
        last = samples[-1] if samples else None
        # Skip the endpoint only if the previous sample is already effectively on it.
        if last is None or total - last.distance_miles > 0.05:
            samples.append(SampledPoint(index=index, lat=points[-1][0], lon=points[-1][1], distance_miles=total))
    return samples


def decode_polyline(encoded: str, precision: int = 5) -> list[tuple[float, float]]:
    """Decode an encoded polyline (OSRM's default geometry format)."""
    coords: list[tuple[float, float]] = []
    index = lat = lon = 0
    factor = float(10**precision)
    length = len(encoded)
    while index < length:
        for axis in range(2):
            shift = result = 0
            while True:
                byte = ord(encoded[index]) - 63
                index += 1
                result |= (byte & 0x1F) << shift
                shift += 5
                if byte < 0x20:
                    break
            delta = ~(result >> 1) if result & 1 else (result >> 1)
            if axis == 0:
                lat += delta
            else:
                lon += delta
        coords.append((lat / factor, lon / factor))
    return coords


def bounding_box(points: list[tuple[float, float]]) -> dict[str, float]:
    lats = [p[0] for p in points]
    lons = [p[1] for p in points]
    return {"min_lat": min(lats), "min_lon": min(lons), "max_lat": max(lats), "max_lon": max(lons)}
