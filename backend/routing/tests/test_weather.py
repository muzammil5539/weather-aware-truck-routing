"""Open-Meteo client: batching, unit handling, and hour lookup."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest import mock

from django.core.cache import cache
from django.test import SimpleTestCase

from routing.exceptions import UpstreamError
from routing.services import weather

START = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)


def reading_at(when, *, wind=20.0, rain=0.0, snow=0.0):
    return weather.Reading(
        time=when, temperature_f=40.0, wind_mph=wind, gust_mph=wind + 10,
        rain_in_hr=rain, snow_in_hr=snow, precipitation_in_hr=rain + snow, weather_code=61,
    )


def block(hours=6, wind=20.0, rain=0.0, snow=0.0, start=START):
    times = [(start + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M") for h in range(hours)]
    return {
        "hourly": {
            "time": times,
            "temperature_2m": [40.0] * hours,
            "wind_speed_10m": [wind] * hours,
            "wind_gusts_10m": [wind + 10] * hours,
            "rain": [rain] * hours,
            "snowfall": [snow] * hours,
            "precipitation": [rain + snow] * hours,
            "weather_code": [61] * hours,
        }
    }


class ForecastTestCase(SimpleTestCase):
    """The forecast cache is process-wide, so each test starts from empty."""

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)


class ParsingTests(ForecastTestCase):
    def test_single_location_returns_one_forecast(self):
        with mock.patch.object(weather, "get_json", return_value=block()):
            forecasts = weather.fetch_hourly([(40.0, -105.0)], START, START + timedelta(hours=5))
        self.assertEqual(len(forecasts), 1)
        self.assertEqual(len(forecasts[0].readings), 6)

    def test_many_locations_come_back_in_order(self):
        payload = [block(wind=10.0), block(wind=20.0), block(wind=30.0)]
        with mock.patch.object(weather, "get_json", return_value=payload):
            forecasts = weather.fetch_hourly(
                [(40.0, -105.0), (41.0, -106.0), (42.0, -107.0)], START, START + timedelta(hours=5)
            )
        self.assertEqual([f.readings[0].wind_mph for f in forecasts], [10.0, 20.0, 30.0])

    def test_units_pass_through_unconverted(self):
        """mph and inches are requested from the API, so nothing is converted here."""
        captured = {}

        def capture(provider, url, params=None, **kwargs):
            captured.update(params)
            return block(wind=33.0, rain=0.4, snow=1.2)

        with mock.patch.object(weather, "get_json", side_effect=capture):
            forecasts = weather.fetch_hourly([(40.0, -105.0)], START, START + timedelta(hours=5))

        self.assertEqual(captured["wind_speed_unit"], "mph")
        self.assertEqual(captured["precipitation_unit"], "inch")
        self.assertEqual(captured["timezone"], "UTC")
        reading = forecasts[0].readings[0]
        self.assertEqual((reading.wind_mph, reading.rain_in_hr, reading.snow_in_hr), (33.0, 0.4, 1.2))

    def test_nulls_become_zero(self):
        payload = block()
        payload["hourly"]["rain"] = [None] * 6
        with mock.patch.object(weather, "get_json", return_value=payload):
            forecasts = weather.fetch_hourly([(40.0, -105.0)], START, START + timedelta(hours=5))
        self.assertEqual(forecasts[0].readings[0].rain_in_hr, 0.0)

    def test_a_short_response_falls_through_to_the_backup_provider(self):
        """A malformed primary response is a reason to ask someone else."""
        points = [(40.0, -105.0), (41.0, -106.0)]
        backup = {p: weather.PointForecast([reading_at(START, wind=44.0)]) for p in points}

        with (
            mock.patch.object(weather, "get_json", return_value=[block()]),
            mock.patch.object(weather, "_fetch_met_no", return_value=backup) as fallback,
        ):
            forecasts = weather.fetch_hourly(points, START, START)

        fallback.assert_called_once()
        self.assertEqual(forecasts[0].readings[0].wind_mph, 44.0)

    def test_an_error_is_raised_only_when_every_provider_fails(self):
        points = [(40.0, -105.0), (41.0, -106.0)]
        with (
            mock.patch.object(weather, "get_json", return_value=[block()]),
            mock.patch.object(
                weather, "_fetch_met_no", side_effect=UpstreamError("met.no", "down", status_code=503)
            ),
        ):
            with self.assertRaises(UpstreamError) as caught:
                weather.fetch_hourly(points, START, START)
        self.assertIn("Every provider is unavailable", caught.exception.detail)

    def test_requests_are_chunked(self):
        points = [(40.0 + i * 0.01, -105.0) for i in range(120)]

        def fake(provider, url, params=None, **kwargs):
            return [block() for _ in params["latitude"].split(",")]

        with mock.patch.object(weather, "get_json", side_effect=fake) as get_json:
            forecasts = weather.fetch_hourly(points, START, START + timedelta(hours=5))
        self.assertEqual(len(forecasts), 120)
        self.assertEqual(get_json.call_count, 3)  # 50 + 50 + 20


class LookupTests(ForecastTestCase):
    def setUp(self):
        with mock.patch.object(weather, "get_json", return_value=block(hours=6)):
            self.forecast = weather.fetch_hourly([(40.0, -105.0)], START, START + timedelta(hours=5))[0]

    def test_exact_hour(self):
        reading = self.forecast.at(START + timedelta(hours=2))
        self.assertEqual(reading.time, START + timedelta(hours=2))

    def test_minutes_round_down_into_the_containing_hour(self):
        reading = self.forecast.at(START + timedelta(hours=2, minutes=47))
        self.assertEqual(reading.time, START + timedelta(hours=2))

    def test_beyond_the_window_falls_back_to_the_nearest_hour(self):
        reading = self.forecast.at(START + timedelta(days=30))
        self.assertEqual(reading.time, START + timedelta(hours=5))

    def test_empty_forecast_returns_none(self):
        self.assertIsNone(weather.PointForecast([]).at(START))


class WindowTests(ForecastTestCase):
    def test_dates_are_clamped_to_the_forecast_horizon(self):
        now = datetime.now(timezone.utc)
        start, end = weather.clamp_to_forecast_window(now, now + timedelta(days=90))
        self.assertLessEqual((end - now.date()).days, weather.FORECAST_HORIZON_DAYS)
        self.assertLessEqual(start, end)

    def test_a_past_departure_clamps_to_today(self):
        now = datetime.now(timezone.utc)
        start, _ = weather.clamp_to_forecast_window(now - timedelta(days=10), now)
        self.assertEqual(start, now.date())


class CacheTests(ForecastTestCase):
    """The cache is what keeps a repeated demo off the rate-limited free tier."""

    POINTS = [(40.0, -105.0), (41.0, -106.0)]

    def test_second_call_for_the_same_points_makes_no_request(self):
        with mock.patch.object(weather, "get_json", return_value=[block(), block()]) as get_json:
            weather.fetch_hourly(self.POINTS, START, START + timedelta(hours=5))
            self.assertEqual(get_json.call_count, 1)

        with mock.patch.object(weather, "get_json") as get_json:
            forecasts = weather.fetch_hourly(self.POINTS, START, START + timedelta(hours=5))
            get_json.assert_not_called()
        self.assertEqual(len(forecasts), 2)
        self.assertEqual(len(forecasts[0].readings), 6)

    def test_only_the_uncached_points_are_requested(self):
        with mock.patch.object(weather, "get_json", return_value=block()):
            weather.fetch_hourly([self.POINTS[0]], START, START + timedelta(hours=5))

        captured = {}

        def capture(provider, url, params=None, **kwargs):
            captured.update(params)
            return block()

        with mock.patch.object(weather, "get_json", side_effect=capture) as get_json:
            forecasts = weather.fetch_hourly(self.POINTS, START, START + timedelta(hours=5))

        self.assertEqual(get_json.call_count, 1)
        self.assertEqual(captured["latitude"], "41.0000")  # the cached point is absent
        self.assertEqual(len(forecasts), 2)

    def test_a_different_date_range_is_a_different_entry(self):
        # Dates must be inside the forecast window, or both clamp to today and
        # legitimately share one cache entry.
        soon = datetime.now(timezone.utc) + timedelta(days=1)
        later = soon + timedelta(days=3)

        with mock.patch.object(weather, "get_json", return_value=block(start=soon)) as first:
            weather.fetch_hourly([self.POINTS[0]], soon, soon + timedelta(hours=5))
            self.assertEqual(first.call_count, 1)

        with mock.patch.object(weather, "get_json", return_value=block(start=later)) as second:
            weather.fetch_hourly([self.POINTS[0]], later, later + timedelta(hours=5))
            self.assertEqual(second.call_count, 1)

    def test_repeated_points_in_one_call_are_requested_once(self):
        duplicated = [self.POINTS[0], self.POINTS[1], self.POINTS[0]]
        with mock.patch.object(weather, "get_json", return_value=[block(), block()]) as get_json:
            forecasts = weather.fetch_hourly(duplicated, START, START + timedelta(hours=5))
        self.assertEqual(get_json.call_count, 1)
        self.assertEqual(len(forecasts), 3)


class RateLimitTests(SimpleTestCase):
    def test_a_429_is_not_retried(self):
        """Retrying a rate limit multiplies the load that caused it."""
        from routing.services import http

        self.assertNotIn(429, http.Retry.DEFAULT.status_forcelist or ())
        session = http.get_session()
        retries = session.get_adapter("https://example.com").max_retries
        self.assertNotIn(429, retries.status_forcelist)
        self.assertIn(503, retries.status_forcelist)


class ProviderFallbackTests(ForecastTestCase):
    """The backup provider exists because the free primary tier throttles."""

    POINTS = [(40.0, -105.0)]

    def test_the_backup_is_not_called_when_the_primary_answers(self):
        with (
            mock.patch.object(weather, "get_json", return_value=block()),
            mock.patch.object(weather, "_fetch_met_no") as fallback,
        ):
            weather.fetch_hourly(self.POINTS, START, START + timedelta(hours=5))
        fallback.assert_not_called()

    def test_a_rate_limited_primary_falls_through(self):
        from routing.exceptions import RateLimited

        backup = {self.POINTS[0]: weather.PointForecast([reading_at(START, wind=31.0)])}
        with (
            mock.patch.object(weather, "get_json", side_effect=RateLimited("open-meteo", "60")),
            mock.patch.object(weather, "_fetch_met_no", return_value=backup) as fallback,
        ):
            forecasts = weather.fetch_hourly(self.POINTS, START, START + timedelta(hours=5))
        fallback.assert_called_once()
        self.assertEqual(forecasts[0].readings[0].wind_mph, 31.0)

    def test_fallback_results_are_cached_like_any_other(self):
        backup = {self.POINTS[0]: weather.PointForecast([reading_at(START, wind=12.0)])}
        with (
            mock.patch.object(weather, "get_json", side_effect=UpstreamError("open-meteo", "boom")),
            mock.patch.object(weather, "_fetch_met_no", return_value=backup),
        ):
            weather.fetch_hourly(self.POINTS, START, START + timedelta(hours=5))

        with (
            mock.patch.object(weather, "get_json") as primary,
            mock.patch.object(weather, "_fetch_met_no") as fallback,
        ):
            forecasts = weather.fetch_hourly(self.POINTS, START, START + timedelta(hours=5))
        primary.assert_not_called()
        fallback.assert_not_called()
        self.assertEqual(forecasts[0].readings[0].wind_mph, 12.0)


class MetNoAdapterTests(SimpleTestCase):
    """Unit conversion is where a fallback provider silently goes wrong."""

    PAYLOAD = {
        "properties": {
            "timeseries": [
                {
                    "time": "2026-01-15T12:00:00Z",
                    "data": {
                        "instant": {"details": {"air_temperature": 0.0, "wind_speed": 10.0}},
                        "next_1_hours": {
                            "summary": {"symbol_code": "heavysnow"},
                            "details": {"precipitation_amount": 25.4},
                        },
                    },
                },
                {
                    "time": "2026-01-15T13:00:00Z",
                    "data": {
                        "instant": {"details": {"air_temperature": 20.0, "wind_speed": 5.0}},
                        "next_6_hours": {
                            "summary": {"symbol_code": "rain"},
                            "details": {"precipitation_amount": 6.0},
                        },
                    },
                },
            ]
        }
    }

    def test_converts_si_units_to_the_risk_table_units(self):
        from routing.services import met_no

        with mock.patch.object(met_no, "get_json", return_value=self.PAYLOAD):
            forecast = met_no.fetch_point((39.7, -105.0))

        first = forecast.readings[0]
        self.assertAlmostEqual(first.wind_mph, 22.37, places=1)   # 10 m/s
        self.assertAlmostEqual(first.temperature_f, 32.0, places=1)  # 0 C
        self.assertAlmostEqual(first.snow_in_hr, 1.0, places=3)   # 25.4 mm
        self.assertEqual(first.rain_in_hr, 0.0)

    def test_six_hour_blocks_are_spread_across_their_hours(self):
        from routing.services import met_no

        with mock.patch.object(met_no, "get_json", return_value=self.PAYLOAD):
            forecast = met_no.fetch_point((39.7, -105.0))

        second = forecast.readings[1]
        self.assertAlmostEqual(second.rain_in_hr, (6.0 / 6) / 25.4, places=4)
        self.assertEqual(second.snow_in_hr, 0.0)

    def test_snow_and_rain_are_split_by_symbol(self):
        from routing.services import met_no

        with mock.patch.object(met_no, "get_json", return_value=self.PAYLOAD):
            forecast = met_no.fetch_point((39.7, -105.0))

        self.assertGreater(forecast.readings[0].snow_in_hr, 0)
        self.assertGreater(forecast.readings[1].rain_in_hr, 0)
