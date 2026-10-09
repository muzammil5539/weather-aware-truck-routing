"""Every boundary in the assessment's risk and load tables."""
from django.test import SimpleTestCase

from routing.services.risk import (
    RiskLevel,
    apply_load_rules,
    assess,
    classify_rain,
    classify_snow,
    classify_wind,
)


class WindBandTests(SimpleTestCase):
    def test_bands(self):
        cases = [
            (0, RiskLevel.LOW), (24.9, RiskLevel.LOW),
            (25, RiskLevel.MODERATE), (34.9, RiskLevel.MODERATE),
            (35, RiskLevel.HIGH), (44.9, RiskLevel.HIGH),
            (45, RiskLevel.SEVERE), (54.9, RiskLevel.SEVERE),
            (55, RiskLevel.NO_TRAVEL), (120, RiskLevel.NO_TRAVEL),
        ]
        for mph, expected in cases:
            with self.subTest(mph=mph):
                self.assertIs(classify_wind(mph), expected)


class RainBandTests(SimpleTestCase):
    def test_bands(self):
        cases = [
            (0, RiskLevel.LOW), (0.099, RiskLevel.LOW),
            (0.10, RiskLevel.MODERATE), (0.249, RiskLevel.MODERATE),
            (0.25, RiskLevel.HIGH), (0.499, RiskLevel.HIGH),
            (0.50, RiskLevel.SEVERE), (1.00, RiskLevel.SEVERE),
            (1.01, RiskLevel.NO_TRAVEL),
        ]
        for value, expected in cases:
            with self.subTest(rain=value):
                self.assertIs(classify_rain(value), expected)


class SnowBandTests(SimpleTestCase):
    def test_bands(self):
        cases = [
            (0, RiskLevel.LOW), (0.49, RiskLevel.LOW),
            (0.5, RiskLevel.MODERATE), (0.99, RiskLevel.MODERATE),
            (1.0, RiskLevel.HIGH), (1.99, RiskLevel.HIGH),
            (2.0, RiskLevel.SEVERE), (3.0, RiskLevel.SEVERE),
            (3.01, RiskLevel.NO_TRAVEL),
        ]
        for value, expected in cases:
            with self.subTest(snow=value):
                self.assertIs(classify_snow(value), expected)


class LoadRuleTests(SimpleTestCase):
    def test_hurricane_wind_blocks_any_load(self):
        self.assertIs(apply_load_rules(55, 0), RiskLevel.NO_TRAVEL)
        self.assertIs(apply_load_rules(80, 80_000), RiskLevel.NO_TRAVEL)

    def test_heavy_load_in_severe_wind_blocks(self):
        self.assertIs(apply_load_rules(45, 30_001), RiskLevel.NO_TRAVEL)
        self.assertIs(apply_load_rules(54, 45_000), RiskLevel.NO_TRAVEL)

    def test_heavy_load_at_exactly_the_threshold_does_not_escalate(self):
        self.assertIs(apply_load_rules(45, 30_000), RiskLevel.LOW)
        self.assertIs(apply_load_rules(35, 40_000), RiskLevel.LOW)

    def test_very_heavy_load_in_high_wind_escalates_to_severe(self):
        self.assertIs(apply_load_rules(35, 40_001), RiskLevel.SEVERE)
        self.assertIs(apply_load_rules(44, 50_000), RiskLevel.SEVERE)

    def test_light_load_is_never_escalated(self):
        for wind in (10, 25, 35, 44, 45, 54):
            with self.subTest(wind=wind):
                self.assertIs(apply_load_rules(wind, 10_000), RiskLevel.LOW)


class AssessTests(SimpleTestCase):
    def test_worst_condition_wins(self):
        result = assess(wind_mph=10, rain_in_hr=0.0, snow_in_hr=2.5, load_lb=10_000)
        self.assertIs(result.level, RiskLevel.SEVERE)
        self.assertEqual(result.driver, "snow")

    def test_load_rule_raises_above_the_weather_band(self):
        # Wind alone is High; a 41,000 lb load makes it Severe.
        weather_only = assess(wind_mph=38, rain_in_hr=0, snow_in_hr=0, load_lb=1_000)
        with_load = assess(wind_mph=38, rain_in_hr=0, snow_in_hr=0, load_lb=41_000)
        self.assertIs(weather_only.level, RiskLevel.HIGH)
        self.assertIs(with_load.level, RiskLevel.SEVERE)
        self.assertEqual(with_load.driver, "load")

    def test_load_rule_never_lowers_a_worse_weather_band(self):
        result = assess(wind_mph=20, rain_in_hr=1.5, snow_in_hr=0, load_lb=1_000)
        self.assertIs(result.level, RiskLevel.NO_TRAVEL)
        self.assertEqual(result.driver, "rain")

    def test_calm_weather_is_low(self):
        result = assess(wind_mph=5, rain_in_hr=0.01, snow_in_hr=0, load_lb=79_000)
        self.assertIs(result.level, RiskLevel.LOW)

    def test_negative_readings_are_treated_as_zero(self):
        self.assertIs(assess(wind_mph=-3, rain_in_hr=-1, snow_in_hr=-1, load_lb=0).level, RiskLevel.LOW)

    def test_serialisable(self):
        payload = assess(wind_mph=46, rain_in_hr=0, snow_in_hr=0, load_lb=31_000).as_dict()
        self.assertEqual(payload["level"], "no_travel")
        self.assertEqual(payload["level_label"], "No Travel")
        self.assertEqual(payload["score"], 4)
