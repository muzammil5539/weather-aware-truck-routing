"""Weather risk classification.

This module is pure: no I/O, no Django. Every threshold in the assessment's
risk table and load table lives here and nowhere else.

Risk table (per checkpoint)

    Condition   Low        Moderate     High         Severe       No Travel
    Wind (mph)  <25        25-34        35-44        45-54        >=55
    Rain (in/hr) <0.10     0.10-0.25    0.25-0.50    0.50-1.00    >1.00
    Snow (in/hr) <0.5      0.5-1.0      1.0-2.0      2.0-3.0      >3.0

Band edges are read as lower-inclusive / upper-exclusive, so rain of exactly
0.25 in/hr is High, not Moderate. The published table only states a strict
inequality at the No Travel edge (">1.00", ">3.0", ">=55"), so the Severe band
is the one that also includes its upper edge. See docs/ASSUMPTIONS.md.

Load rules (escalation applied on top of the weather band)

    wind >= 55 mph                      -> No Travel for any load
    wind 45-54 mph and load > 30,000 lb -> No Travel
    wind 35-44 mph and load > 40,000 lb -> Severe
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class RiskLevel(IntEnum):
    """Ordered so that `max()` picks the worse of two levels."""

    LOW = 0
    MODERATE = 1
    HIGH = 2
    SEVERE = 3
    NO_TRAVEL = 4

    @property
    def label(self) -> str:
        return {
            RiskLevel.LOW: "Low",
            RiskLevel.MODERATE: "Moderate",
            RiskLevel.HIGH: "High",
            RiskLevel.SEVERE: "Severe",
            RiskLevel.NO_TRAVEL: "No Travel",
        }[self]

    @property
    def slug(self) -> str:
        return self.name.lower()


# Upper edge of each band, in ascending order of severity. A reading strictly
# below the edge lands in that band; falling off the end is NO_TRAVEL.
_WIND_EDGES_MPH = ((25.0, RiskLevel.LOW), (35.0, RiskLevel.MODERATE), (45.0, RiskLevel.HIGH), (55.0, RiskLevel.SEVERE))
_RAIN_EDGES_IN_HR = ((0.10, RiskLevel.LOW), (0.25, RiskLevel.MODERATE), (0.50, RiskLevel.HIGH), (1.00, RiskLevel.SEVERE))
_SNOW_EDGES_IN_HR = ((0.5, RiskLevel.LOW), (1.0, RiskLevel.MODERATE), (2.0, RiskLevel.HIGH), (3.0, RiskLevel.SEVERE))

# The Severe band includes its own upper edge (rain exactly 1.00 in/hr is
# Severe; No Travel starts strictly above it). Wind is the exception: the table
# says ">=55", so 55.0 mph itself is No Travel.
_INCLUSIVE_TOP_EDGE = {"wind": False, "rain": True, "snow": True}

NO_TRAVEL_WIND_MPH = 55.0
HEAVY_LOAD_LB = 30_000.0
VERY_HEAVY_LOAD_LB = 40_000.0


def _classify(value: float, edges: tuple[tuple[float, RiskLevel], ...], inclusive_top: bool) -> RiskLevel:
    for edge, level in edges:
        if value < edge:
            return level
    top_edge = edges[-1][0]
    if inclusive_top and value == top_edge:
        return RiskLevel.SEVERE
    return RiskLevel.NO_TRAVEL


def classify_wind(mph: float) -> RiskLevel:
    return _classify(max(0.0, mph), _WIND_EDGES_MPH, _INCLUSIVE_TOP_EDGE["wind"])


def classify_rain(inches_per_hour: float) -> RiskLevel:
    return _classify(max(0.0, inches_per_hour), _RAIN_EDGES_IN_HR, _INCLUSIVE_TOP_EDGE["rain"])


def classify_snow(inches_per_hour: float) -> RiskLevel:
    return _classify(max(0.0, inches_per_hour), _SNOW_EDGES_IN_HR, _INCLUSIVE_TOP_EDGE["snow"])


def apply_load_rules(wind_mph: float, load_lb: float) -> RiskLevel:
    """Floor that the load rules impose, independent of the weather bands."""
    if wind_mph >= NO_TRAVEL_WIND_MPH:
        return RiskLevel.NO_TRAVEL
    if 45.0 <= wind_mph < 55.0 and load_lb > HEAVY_LOAD_LB:
        return RiskLevel.NO_TRAVEL
    if 35.0 <= wind_mph < 45.0 and load_lb > VERY_HEAVY_LOAD_LB:
        return RiskLevel.SEVERE
    return RiskLevel.LOW


@dataclass(frozen=True)
class RiskAssessment:
    level: RiskLevel
    wind: RiskLevel
    rain: RiskLevel
    snow: RiskLevel
    load_floor: RiskLevel
    driver: str  # which input produced the final level

    def as_dict(self) -> dict:
        return {
            "level": self.level.slug,
            "level_label": self.level.label,
            "score": int(self.level),
            "wind_level": self.wind.slug,
            "rain_level": self.rain.slug,
            "snow_level": self.snow.slug,
            "load_floor": self.load_floor.slug,
            "driver": self.driver,
        }


def assess(*, wind_mph: float, rain_in_hr: float, snow_in_hr: float, load_lb: float) -> RiskAssessment:
    """Final risk at one checkpoint: worst weather band, raised by the load rules."""
    wind = classify_wind(wind_mph)
    rain = classify_rain(rain_in_hr)
    snow = classify_snow(snow_in_hr)
    load_floor = apply_load_rules(wind_mph, load_lb)

    candidates = {"wind": wind, "rain": rain, "snow": snow, "load": load_floor}
    level = max(candidates.values())
    # Ties resolve to the weather reading over the load rule, so the UI can say
    # "driven by snow" rather than the less specific "driven by load".
    for name in ("snow", "rain", "wind", "load"):
        if candidates[name] == level:
            driver = name
            break
    return RiskAssessment(level=level, wind=wind, rain=rain, snow=snow, load_floor=load_floor, driver=driver)
