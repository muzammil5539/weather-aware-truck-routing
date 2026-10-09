from __future__ import annotations

from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.response import Response

from routing.models import Trip
from routing.repository import save_plan
from routing.serializers import (
    TripListSerializer,
    TripRequestSerializer,
    TripSerializer,
)
from routing.services import geocode
from routing.services.planner import plan_trip
from routing.services.risk import RiskLevel


class TripViewSet(viewsets.ReadOnlyModelViewSet):
    """Plan a trip (POST) and read it back (GET)."""

    queryset = Trip.objects.prefetch_related("routes__checkpoints")
    serializer_class = TripSerializer

    def get_serializer_class(self):
        return TripListSerializer if self.action == "list" else TripSerializer

    def get_queryset(self):
        if self.action == "list":
            return Trip.objects.all()[:25]
        return super().get_queryset()

    def create(self, request, *args, **kwargs):
        form = TripRequestSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        data = form.validated_data

        def pinned(side: str) -> geocode.Place | None:
            lat, lon = data.get(f"{side}_lat"), data.get(f"{side}_lon")
            return None if lat is None or lon is None else geocode.Place(data[side], lat, lon)

        plan = plan_trip(
            origin_query=data["origin"],
            destination_query=data["destination"],
            departure=data["departure_at"],
            load_lb=data["load_lb"],
            interval_miles=data["checkpoint_interval_miles"],
            origin_place=pinned("origin"),
            destination_place=pinned("destination"),
        )
        trip = save_plan(plan)
        trip = self.get_queryset().get(pk=trip.pk)
        return Response(TripSerializer(trip).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def heatmap(self, request, pk=None):
        """The corridor heatmap on its own, for clients that poll just the grid."""
        return Response(self.get_object().heatmap)


@api_view(["GET"])
def geocode_search(request):
    """Place suggestions for the origin/destination inputs."""
    query = request.query_params.get("q", "")
    results = geocode.search(query, limit=6)
    return Response({"results": [place.as_dict() for place in results]})


@api_view(["GET"])
def risk_reference(request):
    """The thresholds the UI renders in its legend, served from the one source."""
    from routing.services import risk

    return Response(
        {
            "levels": [
                {"slug": level.slug, "label": level.label, "score": int(level)}
                for level in RiskLevel
            ],
            "thresholds": {
                "wind_mph": [25, 35, 45, 55],
                "rain_in_hr": [0.10, 0.25, 0.50, 1.00],
                "snow_in_hr": [0.5, 1.0, 2.0, 3.0],
            },
            "load_rules": [
                {"wind_mph": ">= 55", "load_lb": "any", "level": RiskLevel.NO_TRAVEL.slug},
                {"wind_mph": "45-54", "load_lb": "> 30,000", "level": RiskLevel.NO_TRAVEL.slug},
                {"wind_mph": "35-44", "load_lb": "> 40,000", "level": RiskLevel.SEVERE.slug},
            ],
            "heavy_load_lb": risk.HEAVY_LOAD_LB,
            "very_heavy_load_lb": risk.VERY_HEAVY_LOAD_LB,
        }
    )


@api_view(["GET"])
def health(request):
    return Response({"status": "ok"})
