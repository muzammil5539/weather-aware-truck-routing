"""Persisted trips. The normalised rows are the source of truth for responses;
only the corridor heatmap, which is a dense numeric grid, is stored as JSON.
"""
from __future__ import annotations

import uuid

from django.db import models

from routing.services.planner import CHECKPOINT_INTERVALS_MILES
from routing.services.risk import RiskLevel

RISK_CHOICES = [(level.slug, level.label) for level in RiskLevel]
INTERVAL_CHOICES = [(n, f"{n} miles") for n in CHECKPOINT_INTERVALS_MILES]


class Trip(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    origin_label = models.CharField(max_length=512)
    origin_lat = models.FloatField()
    origin_lon = models.FloatField()
    destination_label = models.CharField(max_length=512)
    destination_lat = models.FloatField()
    destination_lon = models.FloatField()
    departure_at = models.DateTimeField()
    load_lb = models.FloatField()
    checkpoint_interval_miles = models.PositiveSmallIntegerField(
        choices=INTERVAL_CHOICES, default=25
    )
    heatmap = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.origin_label} to {self.destination_label} at {self.departure_at:%Y-%m-%d %H:%M}"

    @property
    def recommended_route(self) -> "Route | None":
        return self.routes.filter(is_recommended=True).first()


class Route(models.Model):
    trip = models.ForeignKey(Trip, related_name="routes", on_delete=models.CASCADE)
    name = models.CharField(max_length=64)
    summary = models.CharField(max_length=256, blank=True)
    distance_miles = models.FloatField()
    duration_hours = models.FloatField()
    arrival_at = models.DateTimeField()
    geometry = models.JSONField(default=list)
    rank = models.PositiveSmallIntegerField()
    is_recommended = models.BooleanField(default=False)
    average_risk = models.FloatField(default=0.0)
    worst_level = models.CharField(max_length=16, choices=RISK_CHOICES, default=RiskLevel.LOW.slug)
    no_travel_miles = models.FloatField(default=0.0)
    severe_miles = models.FloatField(default=0.0)
    high_miles = models.FloatField(default=0.0)
    moderate_miles = models.FloatField(default=0.0)
    low_miles = models.FloatField(default=0.0)
    warnings = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["rank"]
        constraints = [
            models.UniqueConstraint(fields=["trip", "name"], name="unique_route_name_per_trip")
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.distance_miles:.0f} mi)"


class Checkpoint(models.Model):
    route = models.ForeignKey(Route, related_name="checkpoints", on_delete=models.CASCADE)
    index = models.PositiveIntegerField()
    lat = models.FloatField()
    lon = models.FloatField()
    distance_miles = models.FloatField()
    segment_miles = models.FloatField(default=0.0)
    eta = models.DateTimeField()
    weather = models.JSONField(default=dict, blank=True)
    risk_level = models.CharField(max_length=16, choices=RISK_CHOICES)
    risk_score = models.PositiveSmallIntegerField(default=0)
    wind_level = models.CharField(max_length=16, choices=RISK_CHOICES)
    rain_level = models.CharField(max_length=16, choices=RISK_CHOICES)
    snow_level = models.CharField(max_length=16, choices=RISK_CHOICES)
    driver = models.CharField(max_length=16, default="wind")

    class Meta:
        ordering = ["index"]
        constraints = [
            models.UniqueConstraint(fields=["route", "index"], name="unique_checkpoint_per_route")
        ]

    def __str__(self) -> str:
        return f"#{self.index} at {self.distance_miles:.0f} mi: {self.risk_level}"
