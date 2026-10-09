"""Hourly forecasts from Open-Meteo. Free, no API key.

Open-Meteo accepts many coordinates in a single request, so a whole trip's
checkpoints cost one HTTP round trip rather than one per checkpoint. Units are
requested directly in the units the risk table uses (mph, inches per hour), so
nothing downstream has to convert.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from django.conf import settings
from django.core.cache import cache

from routing.exceptions import UpstreamError
from routing.services.fallback import first_success
from routing.services.http import get_json

HOURLY_VARIABLES = (
    "temperature_2m",
    "wind_speed_10m",
    "wind_gusts_10m",
    "rain",
    "snowfall",
    "precipitation",
    "weather_code",
)
MAX_LOCATIONS_PER_REQUEST = 50
FORECAST_HORIZON_DAYS = 16
# Open-Meteo prices a request by how many locations it carries, so a trip costs
# roughly one call per checkpoint against a free tier. Forecasts only change
# hourly, so caching each point turns a repeated demo of the same route into
# zero upstream calls.
CACHE_TTL_SECONDS = 1800
CACHE_VERSION = "v1"


@dataclass(frozen=True)
class Reading:
    time: datetime
    temperature_f: float
    wind_mph: float
    gust_mph: float
    rain_in_hr: float
    snow_in_hr: float
    precipitation_in_hr: float
    weather_code: int

    def as_dict(self) -> dict:
        return {
            "time": self.time.isoformat(),
            "temperature_f": round(self.temperature_f, 1),
            "wind_mph": round(self.wind_mph, 1),
            "gust_mph": round(self.gust_mph, 1),
            "rain_in_hr": round(self.rain_in_hr, 3),
            "snow_in_hr": round(self.snow_in_hr, 3),
            "precipitation_in_hr": round(self.precipitation_in_hr, 3),
            "weather_code": self.weather_code,
        }


class PointForecast:
    """Hourly readings for one coordinate, with lookup by wall-clock time."""

    def __init__(self, readings: list[Reading]):
        self.readings = readings
        self._by_hour = {r.time.replace(minute=0, second=0, microsecond=0): r for r in readings}

    def at(self, when: datetime) -> Reading | None:
        """The reading for the hour containing `when`, or the nearest one held."""
        if not self.readings:
            return None
        when = when.astimezone(timezone.utc)
        exact = self._by_hour.get(when.replace(minute=0, second=0, microsecond=0))
        if exact is not None:
            return exact
        # Outside the forecast window (a departure weeks out, say): fall back to
        # the closest hour we do have rather than dropping the checkpoint.
        return min(self.readings, key=lambda r: abs((r.time - when).total_seconds()))

    def __bool__(self) -> bool:
        return bool(self.readings)


def _float(values: list, i: int) -> float:
    try:
        value = values[i]
    except (IndexError, TypeError):
        return 0.0
    return 0.0 if value is None else float(value)


def _parse_point(block: dict) -> PointForecast:
    hourly = block.get("hourly") or {}
    times = hourly.get("time") or []
    readings: list[Reading] = []
    for i, stamp in enumerate(times):
        try:
            moment = datetime.fromisoformat(stamp).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        readings.append(
            Reading(
                time=moment,
                temperature_f=_float(hourly.get("temperature_2m", []), i),
                wind_mph=_float(hourly.get("wind_speed_10m", []), i),
                gust_mph=_float(hourly.get("wind_gusts_10m", []), i),
                rain_in_hr=_float(hourly.get("rain", []), i),
                snow_in_hr=_float(hourly.get("snowfall", []), i),
                precipitation_in_hr=_float(hourly.get("precipitation", []), i),
                weather_code=int(_float(hourly.get("weather_code", []), i)),
            )
        )
    return PointForecast(readings)


def clamp_to_forecast_window(start: datetime, end: datetime) -> tuple[date, date]:
    """Dates Open-Meteo will actually serve, as a (start_date, end_date) pair."""
    today = datetime.now(timezone.utc).date()
    horizon = today + timedelta(days=FORECAST_HORIZON_DAYS - 1)
    start_date = min(max(start.astimezone(timezone.utc).date(), today), horizon)
    end_date = min(max(end.astimezone(timezone.utc).date(), start_date), horizon)
    return start_date, end_date


def _cache_key(point: tuple[float, float], start: date, end: date) -> str:
    return f"om:{CACHE_VERSION}:{point[0]:.4f},{point[1]:.4f}:{start}:{end}"


def _fetch_open_meteo(
    points: list[tuple[float, float]], start_date: date, end_date: date
) -> dict[tuple[float, float], PointForecast]:
    """The primary provider: many coordinates per request."""
    out: dict[tuple[float, float], PointForecast] = {}
    for chunk_start in range(0, len(points), MAX_LOCATIONS_PER_REQUEST):
        chunk = points[chunk_start : chunk_start + MAX_LOCATIONS_PER_REQUEST]
        payload = get_json(
            "open-meteo",
            settings.OPEN_METEO_BASE_URL,
            params={
                "latitude": ",".join(f"{lat:.4f}" for lat, _ in chunk),
                "longitude": ",".join(f"{lon:.4f}" for _, lon in chunk),
                "hourly": ",".join(HOURLY_VARIABLES),
                "wind_speed_unit": "mph",
                "precipitation_unit": "inch",
                "temperature_unit": "fahrenheit",
                "timezone": "UTC",
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
        )
        # A single coordinate comes back as an object; several come back as a list.
        blocks = payload if isinstance(payload, list) else [payload]
        if len(blocks) != len(chunk):
            raise UpstreamError(
                "open-meteo", f"Expected {len(chunk)} forecasts, received {len(blocks)}."
            )
        out.update({point: _parse_point(block) for point, block in zip(chunk, blocks)})
    return out


def _fetch_met_no(points: list[tuple[float, float]]) -> dict[tuple[float, float], PointForecast]:
    """The fallback provider: one coordinate per request, fanned out."""
    from routing.services import met_no

    return met_no.fetch_many(points)


def fetch_hourly(
    points: list[tuple[float, float]], start: datetime, end: datetime
) -> list[PointForecast]:
    """One forecast per input point, in the same order.

    Points already held in the cache are not requested again; only the misses
    go upstream, and only to the fallback provider if the primary is throttling.
    """
    if not points:
        return []

    start_date, end_date = clamp_to_forecast_window(start, end)

    resolved: dict[tuple[float, float], PointForecast] = {}
    misses: list[tuple[float, float]] = []
    pending: set[tuple[float, float]] = set()
    for point in points:
        if point in resolved or point in pending:
            continue  # the same coordinate twice is still one forecast
        cached = cache.get(_cache_key(point, start_date, end_date))
        if cached is not None:
            resolved[point] = PointForecast(cached)
        else:
            pending.add(point)
            misses.append(point)

    if misses:
        fetched = first_success(
            [
                ("open-meteo", lambda: _fetch_open_meteo(misses, start_date, end_date)),
                ("met.no", lambda: _fetch_met_no(misses)),
            ],
            "weather",
        )
        for point, forecast in fetched.items():
            resolved[point] = forecast
            cache.set(_cache_key(point, start_date, end_date), forecast.readings, CACHE_TTL_SECONDS)

    return [resolved[point] for point in points]
