"""Place lookup via Nominatim (OpenStreetMap). Free, no API key."""
from __future__ import annotations

import re
from dataclasses import dataclass

from django.conf import settings

from routing.exceptions import GeocodingError
from routing.services.http import get_json

_LATLON = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")


@dataclass(frozen=True)
class Place:
    label: str
    lat: float
    lon: float

    def as_dict(self) -> dict:
        return {"label": self.label, "lat": self.lat, "lon": self.lon}


def search(query: str, limit: int = 5) -> list[Place]:
    """Place suggestions for a free-text query, biased to North America."""
    query = query.strip()
    if len(query) < 2:
        return []

    if match := _LATLON.match(query):
        lat, lon = float(match.group(1)), float(match.group(2))
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            return [Place(label=f"{lat:.5f}, {lon:.5f}", lat=lat, lon=lon)]

    payload = get_json(
        "nominatim",
        f"{settings.NOMINATIM_BASE_URL}/search",
        params={
            "q": query,
            "format": "jsonv2",
            "limit": limit,
            "addressdetails": 0,
            "countrycodes": "us,ca,mx",
        },
    )
    if not isinstance(payload, list):
        raise GeocodingError("Unexpected response from the geocoder.")
    return [
        Place(label=item["display_name"], lat=float(item["lat"]), lon=float(item["lon"]))
        for item in payload
        if "lat" in item and "lon" in item
    ]


def resolve(query: str) -> Place:
    """The single best match for a place name. Raises if nothing matches."""
    results = search(query, limit=1)
    if not results:
        raise GeocodingError(f"Could not find a place matching {query!r}.")
    return results[0]
