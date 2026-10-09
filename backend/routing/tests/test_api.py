"""API contract: validation, the planning round trip, and upstream failures."""
from __future__ import annotations

from datetime import timezone
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from routing.exceptions import GeocodingError, NoRouteFound, UpstreamError
from routing.models import Checkpoint, Route, Trip
from routing.services import planner
from routing.tests import factories

VALID_PAYLOAD = {
    "origin": "Denver, CO",
    "destination": "Salt Lake City, UT",
    "departure_at": "2026-01-15T12:00:00Z",
    "load_lb": 42000,
    "checkpoint_interval_miles": 25,
}


def patched_upstreams(routes=None, fetch_hourly=None):
    routes = routes or [
        factories.make_route("Route A", distance_miles=520, duration_hours=8),
        factories.make_route("Route B", distance_miles=540, duration_hours=8.5, lat_offset=0.6),
    ]
    return (
        mock.patch.object(planner.geocode, "resolve", side_effect=[factories.ORIGIN, factories.DESTINATION]),
        mock.patch.object(planner.osrm, "fetch_routes", return_value=routes),
        mock.patch.object(planner.weather, "fetch_hourly", side_effect=fetch_hourly or factories.CALM),
    )


class TripCreateTests(TestCase):
    url = reverse("trip-list")

    def post(self, payload=None, **patch_kwargs):
        patches = patched_upstreams(**patch_kwargs)
        for p in patches:
            p.start()
        try:
            return self.client.post(self.url, payload or VALID_PAYLOAD, content_type="application/json")
        finally:
            for p in patches:
                p.stop()

    def test_creates_a_trip_with_routes_and_checkpoints(self):
        response = self.post()
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()

        self.assertEqual(Trip.objects.count(), 1)
        self.assertEqual(Route.objects.count(), 2)
        self.assertGreater(Checkpoint.objects.count(), 10)

        self.assertEqual(len(body["routes"]), 2)
        self.assertIsNotNone(body["recommended_route"])
        self.assertEqual(body["origin"]["label"], factories.ORIGIN.label)
        self.assertEqual(body["load_lb"], 42000)

    def test_response_shape_is_complete(self):
        body = self.post().json()
        route = body["routes"][0]
        for key in (
            "name", "summary", "distance_miles", "duration_hours", "arrival_at", "geometry",
            "rank", "is_recommended", "average_risk", "worst_level", "risk_miles", "checkpoints",
        ):
            self.assertIn(key, route)
        checkpoint = route["checkpoints"][0]
        for key in ("index", "lat", "lon", "distance_miles", "eta", "weather", "risk_level", "risk_score"):
            self.assertIn(key, checkpoint)
        self.assertEqual(len(body["heatmap"]["hours"]), planner.HEATMAP_HOURS)

    def test_exactly_one_route_is_recommended_and_ranked_first(self):
        body = self.post().json()
        recommended = [r for r in body["routes"] if r["is_recommended"]]
        self.assertEqual(len(recommended), 1)
        self.assertEqual(recommended[0]["rank"], 1)
        self.assertEqual(body["recommended_route"], recommended[0]["name"])
        self.assertEqual([r["rank"] for r in body["routes"]], [1, 2])

    def test_pinned_coordinates_skip_the_geocoder(self):
        payload = {**VALID_PAYLOAD, "origin_lat": 39.7392, "origin_lon": -104.9903}
        with (
            mock.patch.object(planner.geocode, "resolve", return_value=factories.DESTINATION) as resolve,
            mock.patch.object(planner.osrm, "fetch_routes", return_value=[factories.make_route("Route A", distance_miles=520, duration_hours=8)]),
            mock.patch.object(planner.weather, "fetch_hourly", side_effect=factories.CALM),
        ):
            response = self.client.post(self.url, payload, content_type="application/json")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(resolve.call_count, 1)  # destination only

    def test_load_rules_reach_the_stored_checkpoints(self):
        windy = factories.forecast_factory(lambda lat, lon, hour: {"wind": 47.0})
        heavy = self.post({**VALID_PAYLOAD, "load_lb": 31_000}, fetch_hourly=windy).json()
        light = self.post({**VALID_PAYLOAD, "load_lb": 10_000}, fetch_hourly=windy).json()
        self.assertEqual(heavy["routes"][0]["checkpoints"][0]["risk_level"], "no_travel")
        self.assertEqual(light["routes"][0]["checkpoints"][0]["risk_level"], "severe")


class ValidationTests(TestCase):
    url = reverse("trip-list")

    def post(self, payload):
        return self.client.post(self.url, payload, content_type="application/json")

    def test_missing_fields_are_rejected(self):
        response = self.post({"origin": "Denver"})
        self.assertEqual(response.status_code, 400)
        fields = response.json()["error"]["fields"]
        for name in ("destination", "departure_at", "load_lb"):
            self.assertIn(name, fields)

    def test_negative_load_is_rejected(self):
        self.assertEqual(self.post({**VALID_PAYLOAD, "load_lb": -1}).status_code, 400)

    def test_absurd_load_is_rejected(self):
        self.assertEqual(self.post({**VALID_PAYLOAD, "load_lb": 10_000_000}).status_code, 400)

    def test_unsupported_checkpoint_interval_is_rejected(self):
        self.assertEqual(self.post({**VALID_PAYLOAD, "checkpoint_interval_miles": 7}).status_code, 400)

    def test_supported_checkpoint_intervals_are_accepted(self):
        for interval in (10, 25, 50):
            with self.subTest(interval=interval):
                patches = patched_upstreams()
                for p in patches:
                    p.start()
                try:
                    response = self.post({**VALID_PAYLOAD, "checkpoint_interval_miles": interval})
                finally:
                    for p in patches:
                        p.stop()
                self.assertEqual(response.status_code, 201, response.content)

    def test_same_origin_and_destination_is_rejected(self):
        response = self.post({**VALID_PAYLOAD, "destination": "denver, co "})
        self.assertEqual(response.status_code, 400)
        self.assertIn("destination", response.json()["error"]["fields"])

    def test_half_a_coordinate_pair_is_rejected(self):
        self.assertEqual(self.post({**VALID_PAYLOAD, "origin_lat": 39.7}).status_code, 400)

    def test_bad_timestamp_is_rejected(self):
        self.assertEqual(self.post({**VALID_PAYLOAD, "departure_at": "not-a-date"}).status_code, 400)

    def test_naive_timestamp_is_accepted_as_utc(self):
        patches = patched_upstreams()
        for p in patches:
            p.start()
        try:
            response = self.post({**VALID_PAYLOAD, "departure_at": "2026-01-15T12:00:00"})
        finally:
            for p in patches:
                p.stop()
        self.assertEqual(response.status_code, 201, response.content)
        trip = Trip.objects.get()
        self.assertEqual(trip.departure_at.tzinfo, timezone.utc)


class UpstreamFailureTests(TestCase):
    url = reverse("trip-list")

    def post_with(self, exc):
        with mock.patch.object(planner.geocode, "resolve", side_effect=exc):
            return self.client.post(self.url, VALID_PAYLOAD, content_type="application/json")

    def test_unknown_place_returns_422(self):
        response = self.post_with(GeocodingError("Could not find a place matching 'Atlantis'."))
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["provider"], "nominatim")

    def test_no_route_returns_422(self):
        with (
            mock.patch.object(planner.geocode, "resolve", side_effect=[factories.ORIGIN, factories.DESTINATION]),
            mock.patch.object(planner.osrm, "fetch_routes", side_effect=NoRouteFound()),
        ):
            response = self.client.post(self.url, VALID_PAYLOAD, content_type="application/json")
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["type"], "upstream_error")

    def test_weather_outage_returns_502(self):
        with (
            mock.patch.object(planner.geocode, "resolve", side_effect=[factories.ORIGIN, factories.DESTINATION]),
            mock.patch.object(planner.osrm, "fetch_routes", return_value=[factories.make_route("Route A", distance_miles=500, duration_hours=8)]),
            mock.patch.object(planner.weather, "fetch_hourly", side_effect=UpstreamError("open-meteo", "timed out")),
        ):
            response = self.client.post(self.url, VALID_PAYLOAD, content_type="application/json")
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["error"]["provider"], "open-meteo")

    def test_a_failed_plan_stores_nothing(self):
        self.post_with(GeocodingError("nope"))
        self.assertEqual(Trip.objects.count(), 0)


class TripReadTests(TestCase):
    def setUp(self):
        patches = patched_upstreams()
        for p in patches:
            p.start()
        try:
            self.trip_id = self.client.post(
                reverse("trip-list"), VALID_PAYLOAD, content_type="application/json"
            ).json()["id"]
        finally:
            for p in patches:
                p.stop()

    def test_retrieve_returns_the_stored_plan(self):
        response = self.client.get(reverse("trip-detail", args=[self.trip_id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["routes"]), 2)

    def test_unknown_trip_is_404(self):
        response = self.client.get(reverse("trip-detail", args=["6f1c4e4e-0000-4000-8000-000000000000"]))
        self.assertEqual(response.status_code, 404)

    def test_heatmap_endpoint_serves_the_grid_alone(self):
        response = self.client.get(reverse("trip-heatmap", args=[self.trip_id]))
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body["hours"]), planner.HEATMAP_HOURS)
        self.assertEqual(len(body["risk"]), len(body["points"]))

    def test_list_is_lightweight(self):
        body = self.client.get(reverse("trip-list")).json()
        rows = body["results"] if isinstance(body, dict) else body
        self.assertEqual(len(rows), 1)
        self.assertNotIn("routes", rows[0])


class SupportEndpointTests(TestCase):
    def test_health(self):
        self.assertEqual(self.client.get(reverse("health")).json(), {"status": "ok"})

    def test_risk_reference_matches_the_table(self):
        body = self.client.get(reverse("risk-reference")).json()
        self.assertEqual(body["thresholds"]["wind_mph"], [25, 35, 45, 55])
        self.assertEqual(body["thresholds"]["rain_in_hr"], [0.10, 0.25, 0.50, 1.00])
        self.assertEqual(body["thresholds"]["snow_in_hr"], [0.5, 1.0, 2.0, 3.0])
        self.assertEqual([lvl["slug"] for lvl in body["levels"]],
                         ["low", "moderate", "high", "severe", "no_travel"])

    def test_geocode_proxies_suggestions(self):
        with mock.patch("routing.views.geocode.search", return_value=[factories.ORIGIN]) as search:
            response = self.client.get(reverse("geocode"), {"q": "Denver"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"][0]["label"], factories.ORIGIN.label)
        search.assert_called_once()

    def test_geocode_with_a_short_query_returns_nothing(self):
        response = self.client.get(reverse("geocode"), {"q": "D"})
        self.assertEqual(response.json()["results"], [])
