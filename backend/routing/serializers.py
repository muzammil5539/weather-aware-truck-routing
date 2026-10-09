from __future__ import annotations

from datetime import timezone

from django.utils import timezone as dj_timezone
from rest_framework import serializers

from routing.models import Checkpoint, Route, Trip
from routing.services.planner import CHECKPOINT_INTERVALS_MILES

MAX_LOAD_LB = 200_000.0


class TripRequestSerializer(serializers.Serializer):
    """What the planning form submits."""

    origin = serializers.CharField(max_length=512)
    destination = serializers.CharField(max_length=512)
    departure_at = serializers.DateTimeField()
    load_lb = serializers.FloatField(min_value=0.0, max_value=MAX_LOAD_LB)
    checkpoint_interval_miles = serializers.ChoiceField(
        choices=CHECKPOINT_INTERVALS_MILES, default=25
    )
    # Optional: the form sends these when the user picked a geocoder suggestion,
    # which saves a lookup and pins the exact place they chose.
    origin_lat = serializers.FloatField(required=False, min_value=-90, max_value=90)
    origin_lon = serializers.FloatField(required=False, min_value=-180, max_value=180)
    destination_lat = serializers.FloatField(required=False, min_value=-90, max_value=90)
    destination_lon = serializers.FloatField(required=False, min_value=-180, max_value=180)

    def validate_departure_at(self, value):
        if dj_timezone.is_naive(value):
            value = value.replace(tzinfo=timezone.utc)
        return value

    def validate(self, attrs):
        if attrs["origin"].strip().lower() == attrs["destination"].strip().lower():
            raise serializers.ValidationError(
                {"destination": "Destination must differ from the origin."}
            )
        for side in ("origin", "destination"):
            has_lat = f"{side}_lat" in attrs
            has_lon = f"{side}_lon" in attrs
            if has_lat != has_lon:
                raise serializers.ValidationError(
                    {f"{side}_lat": f"Provide both {side}_lat and {side}_lon, or neither."}
                )
        return attrs


class CheckpointSerializer(serializers.ModelSerializer):
    class Meta:
        model = Checkpoint
        fields = (
            "index", "lat", "lon", "distance_miles", "segment_miles", "eta", "weather",
            "risk_level", "risk_score", "wind_level", "rain_level", "snow_level", "driver",
        )


class RouteSerializer(serializers.ModelSerializer):
    checkpoints = CheckpointSerializer(many=True, read_only=True)
    risk_miles = serializers.SerializerMethodField()

    class Meta:
        model = Route
        fields = (
            "name", "summary", "distance_miles", "duration_hours", "arrival_at", "geometry",
            "rank", "is_recommended", "average_risk", "worst_level", "risk_miles", "warnings",
            "checkpoints",
        )

    def get_risk_miles(self, route: Route) -> dict:
        return {
            "no_travel": round(route.no_travel_miles, 1),
            "severe": round(route.severe_miles, 1),
            "high": round(route.high_miles, 1),
            "moderate": round(route.moderate_miles, 1),
            "low": round(route.low_miles, 1),
        }


class TripSerializer(serializers.ModelSerializer):
    routes = RouteSerializer(many=True, read_only=True)
    origin = serializers.SerializerMethodField()
    destination = serializers.SerializerMethodField()
    recommended_route = serializers.SerializerMethodField()

    class Meta:
        model = Trip
        fields = (
            "id", "origin", "destination", "departure_at", "load_lb",
            "checkpoint_interval_miles", "recommended_route", "routes", "heatmap", "created_at",
        )

    def get_origin(self, trip: Trip) -> dict:
        return {"label": trip.origin_label, "lat": trip.origin_lat, "lon": trip.origin_lon}

    def get_destination(self, trip: Trip) -> dict:
        return {
            "label": trip.destination_label,
            "lat": trip.destination_lat,
            "lon": trip.destination_lon,
        }

    def get_recommended_route(self, trip: Trip) -> str | None:
        best = trip.recommended_route
        return best.name if best else None


class TripListSerializer(serializers.ModelSerializer):
    """The lightweight shape used by the recent-trips list; no geometry."""

    class Meta:
        model = Trip
        fields = (
            "id", "origin_label", "destination_label", "departure_at", "load_lb", "created_at"
        )
