"""Open-Meteo client: batching, unit handling, and hour lookup."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest import mock

from django.test import SimpleTestCase

from routing.exceptions import UpstreamError
from routing.services import weather

START = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)


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


class ParsingTests(SimpleTestCase):
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

    def test_a_short_response_is_an_upstream_error(self):
        with mock.patch.object(weather, "get_json", return_value=[block()]):
            with self.assertRaises(UpstreamError):
                weather.fetch_hourly([(40.0, -105.0), (41.0, -106.0)], START, START)

    def test_requests_are_chunked(self):
        points = [(40.0 + i * 0.01, -105.0) for i in range(120)]

        def fake(provider, url, params=None, **kwargs):
            return [block() for _ in params["latitude"].split(",")]

        with mock.patch.object(weather, "get_json", side_effect=fake) as get_json:
            forecasts = weather.fetch_hourly(points, START, START + timedelta(hours=5))
        self.assertEqual(len(forecasts), 120)
        self.assertEqual(get_json.call_count, 3)  # 50 + 50 + 20


class LookupTests(SimpleTestCase):
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


class WindowTests(SimpleTestCase):
    def test_dates_are_clamped_to_the_forecast_horizon(self):
        now = datetime.now(timezone.utc)
        start, end = weather.clamp_to_forecast_window(now, now + timedelta(days=90))
        self.assertLessEqual((end - now.date()).days, weather.FORECAST_HORIZON_DAYS)
        self.assertLessEqual(start, end)

    def test_a_past_departure_clamps_to_today(self):
        now = datetime.now(timezone.utc)
        start, _ = weather.clamp_to_forecast_window(now - timedelta(days=10), now)
        self.assertEqual(start, now.date())
