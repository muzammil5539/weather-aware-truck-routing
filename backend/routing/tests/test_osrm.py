"""OSRM client: parsing, de-duplication, and the detour fallback."""
from __future__ import annotations

from unittest import mock

from django.test import SimpleTestCase

from routing.exceptions import NoRouteFound, UpstreamError
from routing.services import osrm
from routing.services.geo import haversine_miles

DENVER = (39.7392, -104.9903)
SALT_LAKE = (40.7608, -111.8910)


def encoded(points):
    """Encode a polyline, so fixtures can be written as plain coordinates."""
    out, prev_lat, prev_lon = [], 0, 0
    for lat, lon in points:
        for value, prev in ((round(lat * 1e5), prev_lat), (round(lon * 1e5), prev_lon)):
            delta = value - prev
            delta = ~(delta << 1) if delta < 0 else (delta << 1)
            while delta >= 0x20:
                out.append(chr((0x20 | (delta & 0x1F)) + 63))
                delta >>= 5
            out.append(chr(delta + 63))
        prev_lat, prev_lon = round(lat * 1e5), round(lon * 1e5)
    return "".join(out)


def raw_route(points, *, miles, hours, roads=("I 80",)):
    return {
        "geometry": encoded(points),
        "distance": miles * 1609.344,
        "duration": hours * 3600,
        "legs": [{"steps": [{"ref": road, "distance": 1000.0} for road in roads]}],
    }


def line(start, end, steps=20):
    return [
        (start[0] + (end[0] - start[0]) * i / steps, start[1] + (end[1] - start[1]) * i / steps)
        for i in range(steps + 1)
    ]


class ParsingTests(SimpleTestCase):
    def test_parses_distance_duration_and_roads(self):
        payload = {"code": "Ok", "routes": [raw_route(line(DENVER, SALT_LAKE), miles=500, hours=8, roads=("I 80", "I 15"))]}
        with mock.patch.object(osrm, "_request", return_value=payload):
            routes = osrm.fetch_routes(DENVER, SALT_LAKE, count=1)
        self.assertEqual(len(routes), 1)
        self.assertEqual(routes[0].name, "Route A")
        self.assertAlmostEqual(routes[0].distance_miles, 500, places=2)
        self.assertAlmostEqual(routes[0].duration_hours, 8, places=4)
        self.assertEqual(routes[0].source, "osrm")
        self.assertIn("I 80", routes[0].summary)

    def test_routes_are_named_in_order(self):
        far = [(lat + 2.0, lon) for lat, lon in line(DENVER, SALT_LAKE)]
        payload = {
            "code": "Ok",
            "routes": [
                raw_route(line(DENVER, SALT_LAKE), miles=500, hours=8),
                raw_route(far, miles=560, hours=9),
            ],
        }
        with mock.patch.object(osrm, "_request", return_value=payload):
            routes = osrm.fetch_routes(DENVER, SALT_LAKE, count=2)
        self.assertEqual([r.name for r in routes], ["Route A", "Route B"])


class ErrorTests(SimpleTestCase):
    def test_no_route_code_raises(self):
        with mock.patch.object(osrm, "_request", return_value={"code": "NoRoute"}):
            with self.assertRaises(NoRouteFound):
                osrm.fetch_routes(DENVER, SALT_LAKE)

    def test_empty_route_list_raises(self):
        with mock.patch.object(osrm, "_request", return_value={"code": "Ok", "routes": []}):
            with self.assertRaises(NoRouteFound):
                osrm.fetch_routes(DENVER, SALT_LAKE)

    def test_other_error_codes_surface_as_upstream_errors(self):
        with mock.patch.object(osrm, "_request", return_value={"code": "InvalidQuery", "message": "bad"}):
            with self.assertRaises(UpstreamError):
                osrm.fetch_routes(DENVER, SALT_LAKE)


class DeduplicationTests(SimpleTestCase):
    def test_near_identical_alternatives_collapse_to_one(self):
        nearly_same = [(lat + 0.005, lon) for lat, lon in line(DENVER, SALT_LAKE)]
        payload = {
            "code": "Ok",
            "routes": [
                raw_route(line(DENVER, SALT_LAKE), miles=500, hours=8),
                raw_route(nearly_same, miles=502, hours=8.1),
            ],
        }
        with mock.patch.object(osrm, "_request", return_value=payload):
            routes = osrm.fetch_routes(DENVER, SALT_LAKE, count=3)
        # The duplicate is dropped, and two detours fill the gap.
        self.assertEqual(len([r for r in routes if r.source == "osrm"]), 1)


class DetourFallbackTests(SimpleTestCase):
    def test_detours_top_up_a_short_alternative_list(self):
        """OSRM offers one route; the client must still produce three."""
        offsets = iter([3.0, -3.0, 5.0, -5.0, 7.0, -7.0])

        def fake_request(coords, alternatives):
            legs = coords.count(";")
            if legs == 1:
                return {"code": "Ok", "routes": [raw_route(line(DENVER, SALT_LAKE), miles=500, hours=8)]}
            shift = next(offsets)
            detour = [(lat + shift, lon) for lat, lon in line(DENVER, SALT_LAKE)]
            return {"code": "Ok", "routes": [raw_route(detour, miles=560, hours=9.5)]}

        with mock.patch.object(osrm, "_request", side_effect=fake_request):
            routes = osrm.fetch_routes(DENVER, SALT_LAKE, count=3)

        self.assertEqual(len(routes), 3)
        self.assertEqual([r.name for r in routes], ["Route A", "Route B", "Route C"])
        self.assertEqual([r.source for r in routes], ["osrm", "detour", "detour"])

    def test_a_failing_detour_does_not_fail_the_whole_request(self):
        def fake_request(coords, alternatives):
            if coords.count(";") == 1:
                return {"code": "Ok", "routes": [raw_route(line(DENVER, SALT_LAKE), miles=500, hours=8)]}
            raise UpstreamError("osrm", "detour unavailable")

        with mock.patch.object(osrm, "_request", side_effect=fake_request):
            routes = osrm.fetch_routes(DENVER, SALT_LAKE, count=3)
        self.assertEqual(len(routes), 1)

    def test_waypoint_is_offset_to_the_side_of_the_direct_line(self):
        left = osrm._detour_waypoint(DENVER, SALT_LAKE, 0.2)
        right = osrm._detour_waypoint(DENVER, SALT_LAKE, -0.2)
        midpoint = ((DENVER[0] + SALT_LAKE[0]) / 2, (DENVER[1] + SALT_LAKE[1]) / 2)
        direct_miles = haversine_miles(DENVER, SALT_LAKE)

        self.assertAlmostEqual(haversine_miles(midpoint, left), direct_miles * 0.2, delta=direct_miles * 0.05)
        self.assertGreater(haversine_miles(left, right), direct_miles * 0.3)
