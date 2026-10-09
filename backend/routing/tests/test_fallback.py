"""Provider fallback: when to try someone else, and when not to bother."""
from __future__ import annotations

from unittest import mock

from django.test import SimpleTestCase, override_settings

from routing.exceptions import GeocodingError, NoRouteFound, RateLimited, UpstreamError
from routing.services import geocode, osrm
from routing.services.fallback import first_success, is_transient


class PolicyTests(SimpleTestCase):
    def test_rate_limits_and_server_faults_are_worth_another_provider(self):
        self.assertTrue(is_transient(RateLimited("open-meteo")))
        self.assertTrue(is_transient(UpstreamError("osrm", "boom", status_code=502)))
        self.assertTrue(is_transient(UpstreamError("osrm", "down", status_code=503)))

    def test_a_real_answer_is_not_worth_another_provider(self):
        # Every provider would agree there is no road; falling through is waste.
        self.assertFalse(is_transient(NoRouteFound()))
        self.assertFalse(is_transient(GeocodingError("no such place")))


class FirstSuccessTests(SimpleTestCase):
    def test_returns_the_first_provider_that_answers(self):
        second = mock.Mock(return_value="b")
        result = first_success([("a", mock.Mock(return_value="a")), ("b", second)], "x")
        self.assertEqual(result, "a")
        second.assert_not_called()

    def test_falls_through_a_transient_failure(self):
        failing = mock.Mock(side_effect=RateLimited("a"))
        result = first_success([("a", failing), ("b", mock.Mock(return_value="b"))], "x")
        self.assertEqual(result, "b")

    def test_a_definitive_failure_stops_the_chain_immediately(self):
        later = mock.Mock(return_value="b")
        with self.assertRaises(NoRouteFound):
            first_success([("a", mock.Mock(side_effect=NoRouteFound())), ("b", later)], "x")
        later.assert_not_called()

    def test_every_provider_failing_names_them_all(self):
        with self.assertRaises(UpstreamError) as caught:
            first_success(
                [("a", mock.Mock(side_effect=RateLimited("a"))),
                 ("b", mock.Mock(side_effect=RateLimited("b")))],
                "weather",
            )
        self.assertEqual(caught.exception.status_code, 503)
        self.assertIn("a (", caught.exception.detail)
        self.assertIn("b (", caught.exception.detail)


@override_settings(OSRM_BASE_URLS=["https://primary.invalid", "https://mirror.invalid"])
class RoutingFallbackTests(SimpleTestCase):
    OK = {"code": "Ok", "routes": [{"geometry": "_p~iF~ps|U_ulLnnqC", "distance": 1000.0,
                                    "duration": 100.0, "legs": []}]}

    def test_the_mirror_is_used_when_the_primary_throttles(self):
        calls = []

        def fake(provider, url, params=None, **kwargs):
            calls.append(url)
            if "primary" in url:
                raise RateLimited("osrm", "30")
            return self.OK

        with mock.patch.object(osrm, "get_json", side_effect=fake):
            payload = osrm._request("1,2;3,4", 2)

        self.assertEqual(payload["code"], "Ok")
        self.assertEqual(len(calls), 2)
        self.assertIn("mirror.invalid", calls[1])

    def test_the_mirror_is_untouched_when_the_primary_answers(self):
        with mock.patch.object(osrm, "get_json", return_value=self.OK) as get_json:
            osrm._request("1,2;3,4", 2)
        self.assertEqual(get_json.call_count, 1)


class GeocodingFallbackTests(SimpleTestCase):
    PHOTON = {
        "features": [
            {
                "geometry": {"type": "Point", "coordinates": [-104.9847, 39.7392]},
                "properties": {"name": "Denver", "state": "Colorado", "country": "United States"},
            }
        ]
    }

    def test_photon_is_used_when_nominatim_throttles(self):
        def fake(provider, url, params=None, **kwargs):
            if "nominatim" in url:
                raise RateLimited("nominatim")
            return self.PHOTON

        with mock.patch.object(geocode, "get_json", side_effect=fake):
            places = geocode.search("Denver CO")

        self.assertEqual(len(places), 1)
        self.assertEqual(places[0].label, "Denver, Colorado, United States")
        # GeoJSON is longitude-first; getting this backwards puts trucks in China.
        self.assertAlmostEqual(places[0].lat, 39.7392)
        self.assertAlmostEqual(places[0].lon, -104.9847)

    def test_photon_features_without_coordinates_are_skipped(self):
        payload = {"features": [{"geometry": {}, "properties": {"name": "Nowhere"}}]}
        with mock.patch.object(geocode, "get_json", side_effect=[RateLimited("nominatim"), payload]):
            self.assertEqual(geocode.search("nowhere"), [])

    def test_label_skips_missing_and_duplicated_parts(self):
        self.assertEqual(
            geocode._photon_label({"name": "Denver", "city": "Denver", "country": "United States"}),
            "Denver, United States",
        )

    def test_a_lat_lon_query_still_short_circuits_both_providers(self):
        with mock.patch.object(geocode, "get_json") as get_json:
            places = geocode.search("39.7392, -104.9903")
        get_json.assert_not_called()
        self.assertAlmostEqual(places[0].lat, 39.7392)
