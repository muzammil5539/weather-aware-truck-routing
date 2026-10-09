"""Writing a computed TripPlan into the database, in one transaction."""
from __future__ import annotations

from django.db import transaction

from routing.models import Checkpoint, Route, Trip
from routing.services.planner import TripPlan


@transaction.atomic
def save_plan(plan: TripPlan) -> Trip:
    trip = Trip.objects.create(
        origin_label=plan.origin.label,
        origin_lat=plan.origin.lat,
        origin_lon=plan.origin.lon,
        destination_label=plan.destination.label,
        destination_lat=plan.destination.lat,
        destination_lon=plan.destination.lon,
        departure_at=plan.departure,
        load_lb=plan.load_lb,
        checkpoint_interval_miles=plan.interval_miles,
        heatmap=plan.heatmap,
    )

    routes = Route.objects.bulk_create(
        Route(
            trip=trip,
            name=scored.geometry.name,
            summary=scored.geometry.summary,
            distance_miles=scored.geometry.distance_miles,
            duration_hours=scored.geometry.duration_hours,
            arrival_at=scored.arrival,
            geometry=[[round(lat, 5), round(lon, 5)] for lat, lon in scored.geometry.points],
            rank=scored.rank,
            is_recommended=scored.is_recommended,
            average_risk=scored.average_risk,
            worst_level=scored.worst_level.slug,
            no_travel_miles=scored.no_travel_miles,
            severe_miles=scored.severe_miles,
            high_miles=scored.high_miles,
            moderate_miles=scored.moderate_miles,
            low_miles=scored.low_miles,
            warnings=scored.warnings,
        )
        for scored in plan.routes
    )

    Checkpoint.objects.bulk_create(
        Checkpoint(
            route=route,
            index=cp.index,
            lat=cp.lat,
            lon=cp.lon,
            distance_miles=cp.distance_miles,
            segment_miles=cp.segment_miles,
            eta=cp.eta,
            weather=cp.reading.as_dict() if cp.reading else {},
            risk_level=cp.risk.level.slug,
            risk_score=int(cp.risk.level),
            wind_level=cp.risk.wind.slug,
            rain_level=cp.risk.rain.slug,
            snow_level=cp.risk.snow.slug,
            driver=cp.risk.driver,
        )
        for route, scored in zip(routes, plan.routes)
        for cp in scored.checkpoints
    )
    return trip
