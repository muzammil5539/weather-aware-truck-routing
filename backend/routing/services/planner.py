"""Turns a trip request into scored routes, checkpoints, and a corridor heatmap.

The flow is: geocode -> route alternatives -> sample checkpoints -> estimate the
arrival time at each -> one batched weather call -> risk per checkpoint ->
rank the routes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from math import ceil
from datetime import datetime, timedelta, timezone

from routing.services import geocode, osrm, weather
from routing.services.geo import SampledPoint, cumulative_miles, sample_every
from routing.services.risk import RiskLevel, assess

CHECKPOINT_INTERVALS_MILES = (10, 25, 50)
HEATMAP_HOURS = 48
MAX_HEATMAP_POINTS = 60
MIN_HEATMAP_SPACING_MILES = 20.0


@dataclass
class Checkpoint:
    index: int
    lat: float
    lon: float
    distance_miles: float
    segment_miles: float  # stretch of road this checkpoint speaks for
    eta: datetime
    reading: weather.Reading | None
    risk: object  # RiskAssessment

    def as_dict(self) -> dict:
        return {
            "index": self.index,
            "lat": round(self.lat, 5),
            "lon": round(self.lon, 5),
            "distance_miles": round(self.distance_miles, 1),
            "segment_miles": round(self.segment_miles, 1),
            "eta": self.eta.isoformat(),
            "weather": self.reading.as_dict() if self.reading else None,
            "risk": self.risk.as_dict(),
        }


@dataclass
class ScoredRoute:
    geometry: osrm.RouteGeometry
    checkpoints: list[Checkpoint]
    no_travel_miles: float = 0.0
    severe_miles: float = 0.0
    high_miles: float = 0.0
    moderate_miles: float = 0.0
    low_miles: float = 0.0
    average_risk: float = 0.0
    worst_level: RiskLevel = RiskLevel.LOW
    is_recommended: bool = False
    rank: int = 0
    warnings: list[str] = field(default_factory=list)

    @property
    def arrival(self) -> datetime:
        return self.checkpoints[-1].eta

    def rank_key(self) -> tuple:
        """The assessment's preference order, worst-first on each criterion.

        No Travel miles lead because a leg the truck must not drive outranks
        every other consideration; the remaining four are the stated order:
        fewest Severe miles, fewest High miles, lowest average risk, shortest
        travel time.
        """
        return (
            round(self.no_travel_miles, 1),
            round(self.severe_miles, 1),
            round(self.high_miles, 1),
            round(self.average_risk, 4),
            round(self.geometry.duration_hours, 3),
        )

    def as_dict(self) -> dict:
        return {
            **self.geometry.as_dict(),
            "rank": self.rank,
            "is_recommended": self.is_recommended,
            "arrival": self.arrival.isoformat(),
            "worst_level": self.worst_level.slug,
            "worst_level_label": self.worst_level.label,
            "average_risk": round(self.average_risk, 2),
            "risk_miles": {
                "no_travel": round(self.no_travel_miles, 1),
                "severe": round(self.severe_miles, 1),
                "high": round(self.high_miles, 1),
                "moderate": round(self.moderate_miles, 1),
                "low": round(self.low_miles, 1),
            },
            "warnings": self.warnings,
            "checkpoints": [c.as_dict() for c in self.checkpoints],
        }


@dataclass
class TripPlan:
    origin: geocode.Place
    destination: geocode.Place
    departure: datetime
    load_lb: float
    interval_miles: int
    routes: list[ScoredRoute]
    heatmap: dict

    def as_dict(self) -> dict:
        return {
            "origin": self.origin.as_dict(),
            "destination": self.destination.as_dict(),
            "departure": self.departure.isoformat(),
            "load_lb": self.load_lb,
            "checkpoint_interval_miles": self.interval_miles,
            "routes": [r.as_dict() for r in self.routes],
            "recommended_route": next((r.geometry.name for r in self.routes if r.is_recommended), None),
            "heatmap": self.heatmap,
        }


def _eta_for(departure: datetime, distance_miles: float, route: osrm.RouteGeometry) -> datetime:
    """Arrival time at a point on the route.

    ponytail: distance-proportional split of OSRM's total duration. Honest
    within a few minutes over a long haul; upgrade to per-step durations if a
    checkpoint ETA ever needs to be accurate to the minute.
    """
    if route.distance_miles <= 0:
        return departure
    fraction = min(1.0, max(0.0, distance_miles / route.distance_miles))
    return departure + timedelta(hours=route.duration_hours * fraction)


def sample_checkpoints(route: osrm.RouteGeometry, interval_miles: float) -> list[SampledPoint]:
    """Checkpoints every `interval_miles` of the route's own odometer.

    The decoded polyline is a little shorter or longer than the distance OSRM
    reports for the same route (vertex simplification). Sampling on the polyline
    but reporting mile markers against OSRM's distance would make the two drift
    apart, so distances are rescaled onto OSRM's figure: checkpoints then sit at
    exactly 0, interval, 2*interval, ... and the last one at the route distance.
    """
    polyline_miles = cumulative_miles(route.points)[-1]
    if polyline_miles <= 0 or route.distance_miles <= 0:
        return sample_every(route.points, interval_miles)

    scale = route.distance_miles / polyline_miles
    samples = sample_every(route.points, interval_miles / scale)
    return [
        SampledPoint(
            index=s.index,
            lat=s.lat,
            lon=s.lon,
            distance_miles=min(route.distance_miles, s.distance_miles * scale),
        )
        for s in samples
    ]


def _segment_miles(samples: list[SampledPoint], total_miles: float) -> list[float]:
    """Road each checkpoint speaks for: from itself to the next checkpoint."""
    out = []
    for i, sample in enumerate(samples):
        nxt = samples[i + 1].distance_miles if i + 1 < len(samples) else total_miles
        out.append(max(0.0, nxt - sample.distance_miles))
    return out


def _corridor_points(sampled: list[list[SampledPoint]]) -> list[tuple[float, float]]:
    """Points for the heatmap layer, reusing the checkpoints already sampled.

    The corridor *is* the routes, so re-sampling them at a second spacing only
    invented a second set of coordinates to ask the forecast provider about -
    roughly doubling the locations per trip against a rate-limited free tier.
    Thinning the existing checkpoints costs nothing extra and has the better
    property that the heatmap lines up exactly with the rows in the table.
    """
    budget_per_route = max(4, MAX_HEATMAP_POINTS // max(1, len(sampled)))
    points: list[tuple[float, float]] = []

    for samples in sampled:
        if not samples:
            continue
        stride = max(1, ceil(len(samples) / budget_per_route))
        chosen = samples[::stride]
        # Rounded exactly as checkpoint coordinates are, so the two collapse
        # into one forecast lookup rather than two.
        for sample in chosen:
            points.append((round(sample.lat, 4), round(sample.lon, 4)))
        end = (round(samples[-1].lat, 4), round(samples[-1].lon, 4))
        if points and points[-1] != end:
            points.append(end)

    seen: set[tuple[float, float]] = set()
    unique = []
    for point in points:
        if point not in seen:
            seen.add(point)
            unique.append(point)
    return unique[:MAX_HEATMAP_POINTS]


def _build_heatmap(
    points: list[tuple[float, float]], forecasts: list[weather.PointForecast], departure: datetime, load_lb: float
) -> dict:
    """Risk and raw weather at every corridor point for each of the next 48 hours."""
    anchor = departure.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    hours = [anchor + timedelta(hours=h) for h in range(HEATMAP_HOURS)]

    risk_grid, wind_grid, rain_grid, snow_grid = [], [], [], []
    for forecast in forecasts:
        risk_row, wind_row, rain_row, snow_row = [], [], [], []
        for hour in hours:
            reading = forecast.at(hour) if forecast else None
            if reading is None:
                risk_row.append(0)
                wind_row.append(0.0)
                rain_row.append(0.0)
                snow_row.append(0.0)
                continue
            level = assess(
                wind_mph=reading.wind_mph,
                rain_in_hr=reading.rain_in_hr,
                snow_in_hr=reading.snow_in_hr,
                load_lb=load_lb,
            ).level
            risk_row.append(int(level))
            wind_row.append(round(reading.wind_mph, 1))
            rain_row.append(round(reading.rain_in_hr, 3))
            snow_row.append(round(reading.snow_in_hr, 3))
        risk_grid.append(risk_row)
        wind_grid.append(wind_row)
        rain_grid.append(rain_row)
        snow_grid.append(snow_row)

    return {
        "anchor": anchor.isoformat(),
        "hours": [h.isoformat() for h in hours],
        "points": [[lat, lon] for lat, lon in points],
        "risk": risk_grid,
        "wind_mph": wind_grid,
        "rain_in_hr": rain_grid,
        "snow_in_hr": snow_grid,
    }


def _score(route: ScoredRoute) -> None:
    buckets = {level: 0.0 for level in RiskLevel}
    weighted_sum = 0.0
    total = 0.0
    for checkpoint in route.checkpoints:
        miles = checkpoint.segment_miles
        level = checkpoint.risk.level
        buckets[level] += miles
        weighted_sum += int(level) * miles
        total += miles

    route.no_travel_miles = buckets[RiskLevel.NO_TRAVEL]
    route.severe_miles = buckets[RiskLevel.SEVERE]
    route.high_miles = buckets[RiskLevel.HIGH]
    route.moderate_miles = buckets[RiskLevel.MODERATE]
    route.low_miles = buckets[RiskLevel.LOW]
    route.average_risk = (weighted_sum / total) if total > 0 else 0.0
    route.worst_level = max((c.risk.level for c in route.checkpoints), default=RiskLevel.LOW)

    if route.no_travel_miles > 0:
        route.warnings.append(
            f"{route.no_travel_miles:.0f} mi fall under No Travel conditions for this load."
        )
    if route.severe_miles > 0:
        route.warnings.append(f"{route.severe_miles:.0f} mi of Severe conditions.")


def plan_trip(
    *,
    origin_query: str,
    destination_query: str,
    departure: datetime,
    load_lb: float,
    interval_miles: int = 25,
    origin_place: geocode.Place | None = None,
    destination_place: geocode.Place | None = None,
) -> TripPlan:
    origin = origin_place or geocode.resolve(origin_query)
    destination = destination_place or geocode.resolve(destination_query)

    geometries = osrm.fetch_routes((origin.lat, origin.lon), (destination.lat, destination.lon))

    # Sample every route, then resolve all weather in one batched call.
    sampled: list[list[SampledPoint]] = [
        sample_checkpoints(geometry, float(interval_miles)) for geometry in geometries
    ]

    corridor = _corridor_points(sampled)
    checkpoint_coords = [
        (round(s.lat, 4), round(s.lon, 4)) for samples in sampled for s in samples
    ]

    index_of: dict[tuple[float, float], int] = {}
    unique_coords: list[tuple[float, float]] = []
    for coord in checkpoint_coords + corridor:
        if coord not in index_of:
            index_of[coord] = len(unique_coords)
            unique_coords.append(coord)

    latest_arrival = departure + timedelta(hours=max(g.duration_hours for g in geometries))
    window_end = max(latest_arrival, departure + timedelta(hours=HEATMAP_HOURS))
    forecasts = weather.fetch_hourly(unique_coords, departure, window_end)

    def forecast_for(lat: float, lon: float) -> weather.PointForecast:
        return forecasts[index_of[(round(lat, 4), round(lon, 4))]]

    routes: list[ScoredRoute] = []
    for geometry, samples in zip(geometries, sampled):
        segments = _segment_miles(samples, geometry.distance_miles)
        checkpoints = []
        for sample, segment in zip(samples, segments):
            eta = _eta_for(departure, sample.distance_miles, geometry)
            reading = forecast_for(sample.lat, sample.lon).at(eta)
            risk = assess(
                wind_mph=reading.wind_mph if reading else 0.0,
                rain_in_hr=reading.rain_in_hr if reading else 0.0,
                snow_in_hr=reading.snow_in_hr if reading else 0.0,
                load_lb=load_lb,
            )
            checkpoints.append(
                Checkpoint(
                    index=sample.index,
                    lat=sample.lat,
                    lon=sample.lon,
                    distance_miles=sample.distance_miles,
                    segment_miles=segment,
                    eta=eta,
                    reading=reading,
                    risk=risk,
                )
            )
        route = ScoredRoute(geometry=geometry, checkpoints=checkpoints)
        _score(route)
        routes.append(route)

    routes.sort(key=ScoredRoute.rank_key)
    for position, route in enumerate(routes, start=1):
        route.rank = position
        route.is_recommended = position == 1

    heatmap_forecasts = [forecasts[index_of[p]] for p in corridor]
    heatmap = _build_heatmap(corridor, heatmap_forecasts, departure, load_lb)

    return TripPlan(
        origin=origin,
        destination=destination,
        departure=departure,
        load_lb=load_lb,
        interval_miles=interval_miles,
        routes=routes,
        heatmap=heatmap,
    )
