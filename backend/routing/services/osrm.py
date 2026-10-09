"""Route alternatives via the OSRM demo server. Free, no API key.

OSRM's `alternatives` parameter is best-effort: for many city pairs it returns
only one or two routes, because it will not offer an alternative it considers
too similar or too slow. The assessment asks for three options, so when OSRM
runs out we synthesise the remainder by routing through a waypoint offset to
one side of the corridor, which is how a dispatcher would force a different
highway. Detour routes are marked so the UI can say where they came from.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from math import atan2, cos, degrees, radians, sin

from django.conf import settings

from routing.exceptions import NoRouteFound, UpstreamError
from routing.services.fallback import first_success
from routing.services.geo import METERS_PER_MILE, cumulative_miles, decode_polyline, haversine_miles, point_at_distance
from routing.services.http import get_json

logger = logging.getLogger(__name__)

TARGET_ROUTE_COUNT = 3
# How far to push a detour waypoint off the direct line, as a share of the
# direct distance. Alternating signs send successive detours to either side.
DETOUR_OFFSETS = (0.18, -0.18, 0.30, -0.30, 0.45, -0.45)
# Two routes count as the same road if they never diverge by more than this.
DUPLICATE_THRESHOLD_MILES = 5.0
SIGNATURE_SAMPLES = 12


@dataclass(frozen=True)
class RouteGeometry:
    name: str
    distance_miles: float
    duration_hours: float
    points: list[tuple[float, float]]
    summary: str
    source: str = "osrm"  # "osrm" for a native alternative, "detour" for a forced one

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "summary": self.summary,
            "source": self.source,
            "distance_miles": round(self.distance_miles, 1),
            "duration_hours": round(self.duration_hours, 2),
            "geometry": [[lat, lon] for lat, lon in self.points],
        }

    def signature(self) -> list[tuple[float, float]]:
        """Evenly spaced points along the route, for comparing two routes."""
        cumulative = cumulative_miles(self.points)
        total = cumulative[-1]
        return [
            point_at_distance(self.points, cumulative, total * i / (SIGNATURE_SAMPLES - 1))
            for i in range(SIGNATURE_SAMPLES)
        ]


def _is_duplicate(candidate: RouteGeometry, existing: list[RouteGeometry]) -> bool:
    candidate_signature = candidate.signature()
    for other in existing:
        if max(
            haversine_miles(a, b) for a, b in zip(candidate_signature, other.signature())
        ) <= DUPLICATE_THRESHOLD_MILES:
            return True
    return False


def _road_summary(route: dict) -> str:
    """Name the route by the roads it actually spends the most distance on."""
    by_road: dict[str, float] = {}
    for leg in route.get("legs", []):
        for step in leg.get("steps", []):
            name = (step.get("ref") or step.get("name") or "").strip()
            if name:
                by_road[name] = by_road.get(name, 0.0) + step.get("distance", 0.0)
    top = sorted(by_road.items(), key=lambda kv: kv[1], reverse=True)[:3]
    return " / ".join(name for name, _ in top) if top else "Direct route"


def _detour_waypoint(
    origin: tuple[float, float], destination: tuple[float, float], offset: float
) -> tuple[float, float]:
    """A point offset perpendicular to the midpoint of the direct line."""
    mid_lat = (origin[0] + destination[0]) / 2
    mid_lon = (origin[1] + destination[1]) / 2
    direct_miles = haversine_miles(origin, destination)

    # Bearing of the direct line, then a quarter turn to one side.
    lat1, lat2 = radians(origin[0]), radians(destination[0])
    dlon = radians(destination[1] - origin[1])
    bearing = atan2(sin(dlon) * cos(lat2), cos(lat1) * sin(lat2) - sin(lat1) * cos(lat2) * cos(dlon))
    perpendicular = bearing + radians(90)

    miles = direct_miles * offset
    # Degrees per mile: constant for latitude, scaled by cos(lat) for longitude.
    d_lat = (miles * cos(perpendicular)) / 69.0
    d_lon = (miles * sin(perpendicular)) / max(1e-6, 69.0 * cos(radians(mid_lat)))
    return (
        max(-85.0, min(85.0, mid_lat + d_lat)),
        max(-179.0, min(179.0, mid_lon + d_lon)),
    )


def _request(coords: str, alternatives: int) -> dict:
    """Ask each configured OSRM server in turn until one answers.

    Every entry speaks the same protocol, so the mirrors are drop-in: only the
    host differs. The public demo server throttles shared cloud IPs, which is
    exactly when the FOSSGIS mirror earns its place.
    """
    params = {
        "alternatives": str(alternatives) if alternatives > 0 else "false",
        "overview": "full",
        "geometries": "polyline",
        "steps": "true",
    }

    def ask(base: str):
        return lambda: get_json("osrm", f"{base}/route/v1/driving/{coords}", params=params)

    return first_success([(base, ask(base)) for base in settings.OSRM_BASE_URLS], "routing")


def _to_geometry(raw: dict, name: str, source: str) -> RouteGeometry | None:
    points = decode_polyline(raw["geometry"])
    if len(points) < 2:
        return None
    return RouteGeometry(
        name=name,
        distance_miles=raw["distance"] / METERS_PER_MILE,
        duration_hours=raw["duration"] / 3600.0,
        points=points,
        summary=_road_summary(raw),
        source=source,
    )


def fetch_routes(
    origin: tuple[float, float], destination: tuple[float, float], count: int = TARGET_ROUTE_COUNT
) -> list[RouteGeometry]:
    """Up to `count` genuinely distinct driving routes between two points."""
    direct = f"{origin[1]},{origin[0]};{destination[1]},{destination[0]}"
    payload = _request(direct, max(1, count - 1))

    code = payload.get("code")
    if code == "NoRoute":
        raise NoRouteFound()
    if code != "Ok":
        raise UpstreamError("osrm", payload.get("message") or f"Routing failed ({code}).")
    if not payload.get("routes"):
        raise NoRouteFound()

    routes: list[RouteGeometry] = []
    for raw in payload["routes"]:
        geometry = _to_geometry(raw, "pending", "osrm")
        if geometry and not _is_duplicate(geometry, routes):
            routes.append(geometry)
        if len(routes) >= count:
            break

    # OSRM offered fewer than we need: force the rest through a side waypoint.
    for offset in DETOUR_OFFSETS:
        if len(routes) >= count:
            break
        waypoint = _detour_waypoint(origin, destination, offset)
        via = f"{origin[1]},{origin[0]};{waypoint[1]},{waypoint[0]};{destination[1]},{destination[0]}"
        try:
            detour = _request(via, 0)
        except UpstreamError as exc:
            logger.info("Detour request failed, skipping: %s", exc)
            continue
        if detour.get("code") != "Ok" or not detour.get("routes"):
            continue
        geometry = _to_geometry(detour["routes"][0], "pending", "detour")
        if geometry and not _is_duplicate(geometry, routes):
            routes.append(geometry)

    if not routes:
        raise NoRouteFound()

    return [
        RouteGeometry(
            name=f"Route {chr(ord('A') + i)}",
            distance_miles=route.distance_miles,
            duration_hours=route.duration_hours,
            points=route.points,
            summary=route.summary,
            source=route.source,
        )
        for i, route in enumerate(routes[:count])
    ]
