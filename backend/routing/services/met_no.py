"""Fallback forecasts from MET Norway. Free, global, no API key.

Used only when Open-Meteo is unavailable. Two differences from the primary
provider shape the adapter:

* MET serves one coordinate per request, so a trip fans out across a small
  thread pool rather than batching. Their terms ask for an identifying
  User-Agent and modest concurrency.
* MET reports SI units and a single `precipitation_amount`, without splitting
  rain from snow. The hour's `symbol_code` is what distinguishes them, so
  precipitation is attributed to snow when the symbol says snow or sleet and to
  rain otherwise. That is coarser than Open-Meteo's separate fields, and it is
  the reason this is the fallback and not the primary.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from django.conf import settings

from routing.services.http import get_json

logger = logging.getLogger(__name__)

MS_TO_MPH = 2.236936
MM_TO_INCH = 1 / 25.4
SNOW_SYMBOLS = ("snow", "sleet")


def _c_to_f(celsius: float) -> float:
    return celsius * 9 / 5 + 32


def _hour_precipitation(data: dict) -> tuple[float, str]:
    """Precipitation for this hour in mm, and the symbol describing it."""
    one_hour = data.get("next_1_hours")
    if one_hour:
        details = one_hour.get("details") or {}
        summary = one_hour.get("summary") or {}
        return float(details.get("precipitation_amount") or 0.0), str(summary.get("symbol_code", ""))

    # Beyond about two days MET drops to six-hour blocks; spread it evenly
    # rather than reporting zero for five hours out of six.
    six_hour = data.get("next_6_hours")
    if six_hour:
        details = six_hour.get("details") or {}
        summary = six_hour.get("summary") or {}
        return float(details.get("precipitation_amount") or 0.0) / 6.0, str(summary.get("symbol_code", ""))

    return 0.0, ""


def fetch_point(point: tuple[float, float]):
    """Hourly readings for one coordinate, in the primary provider's shape."""
    from routing.services.weather import PointForecast, Reading

    lat, lon = point
    payload = get_json(
        "met.no",
        settings.MET_NO_BASE_URL,
        params={"lat": f"{lat:.4f}", "lon": f"{lon:.4f}"},
    )

    series = ((payload.get("properties") or {}).get("timeseries")) or []
    readings: list[Reading] = []
    for entry in series:
        try:
            moment = datetime.fromisoformat(entry["time"].replace("Z", "+00:00")).astimezone(timezone.utc)
        except (KeyError, ValueError):
            continue

        data = entry.get("data") or {}
        instant = ((data.get("instant") or {}).get("details")) or {}
        amount_mm, symbol = _hour_precipitation(data)

        amount_in = amount_mm * MM_TO_INCH
        is_snow = any(token in symbol for token in SNOW_SYMBOLS)
        wind_mph = float(instant.get("wind_speed") or 0.0) * MS_TO_MPH
        gust = instant.get("wind_speed_of_gust")

        readings.append(
            Reading(
                time=moment,
                temperature_f=_c_to_f(float(instant.get("air_temperature") or 0.0)),
                wind_mph=wind_mph,
                gust_mph=float(gust) * MS_TO_MPH if gust is not None else wind_mph,
                rain_in_hr=0.0 if is_snow else amount_in,
                # MET reports snow as liquid-equivalent depth, the same basis
                # Open-Meteo's snowfall field uses for the risk table.
                snow_in_hr=amount_in if is_snow else 0.0,
                precipitation_in_hr=amount_in,
                weather_code=0,
            )
        )

    return PointForecast(readings)


def fetch_many(points: list[tuple[float, float]]) -> dict[tuple[float, float], object]:
    """Forecasts for several coordinates, fanned out across a small pool."""
    if not points:
        return {}

    workers = max(1, min(settings.MET_NO_MAX_CONCURRENCY, len(points)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(fetch_point, points))
    return dict(zip(points, results))
