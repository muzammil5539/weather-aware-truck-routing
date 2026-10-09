"""Fakes for the three upstream providers, so tests never touch the network."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from routing.services import weather
from routing.services.geocode import Place
from routing.services.osrm import RouteGeometry

ORIGIN = Place(label="Denver, CO", lat=39.7392, lon=-104.9903)
DESTINATION = Place(label="Salt Lake City, UT", lat=40.7608, lon=-111.8910)


def straight_line(start: tuple[float, float], end: tuple[float, float], steps: int = 60):
    """A polyline of evenly spaced points, standing in for a road geometry."""
    return [
        (
            start[0] + (end[0] - start[0]) * i / steps,
            start[1] + (end[1] - start[1]) * i / steps,
        )
        for i in range(steps + 1)
    ]


def make_route(name: str, *, distance_miles: float, duration_hours: float, lat_offset: float = 0.0):
    points = straight_line(
        (ORIGIN.lat + lat_offset, ORIGIN.lon), (DESTINATION.lat + lat_offset, DESTINATION.lon)
    )
    return RouteGeometry(
        name=name,
        distance_miles=distance_miles,
        duration_hours=duration_hours,
        points=points,
        summary=f"{name} roads",
    )


def reading(when: datetime, *, wind=5.0, rain=0.0, snow=0.0) -> weather.Reading:
    return weather.Reading(
        time=when,
        temperature_f=50.0,
        wind_mph=wind,
        gust_mph=wind + 5,
        rain_in_hr=rain,
        snow_in_hr=snow,
        precipitation_in_hr=rain + snow,
        weather_code=0,
    )


def forecast_factory(weather_for_point):
    """Build a fake `weather.fetch_hourly` from a `(lat, lon, hour) -> kwargs` rule."""

    def fetch_hourly(points, start, end):
        anchor = start.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
        hours = int((end - start).total_seconds() // 3600) + 72
        forecasts = []
        for lat, lon in points:
            readings = []
            for h in range(hours):
                when = anchor + timedelta(hours=h)
                readings.append(reading(when, **weather_for_point(lat, lon, h)))
            forecasts.append(weather.PointForecast(readings))
        return forecasts

    return fetch_hourly


CALM = forecast_factory(lambda lat, lon, hour: {"wind": 5.0})
