"""Planner behaviour: checkpoints, ETAs, scoring, and the recommendation order."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest import mock

from django.test import SimpleTestCase

from routing.services import planner
from routing.services.planner import HEATMAP_HOURS, plan_trip
from routing.services.risk import RiskLevel
from routing.tests import factories

DEPARTURE = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)


def run_plan(routes, fetch_hourly, *, load_lb=20_000.0, interval=25):
    with (
        mock.patch.object(planner.osrm, "fetch_routes", return_value=routes),
        mock.patch.object(planner.weather, "fetch_hourly", side_effect=fetch_hourly),
    ):
        return plan_trip(
            origin_query="Denver",
            destination_query="Salt Lake City",
            departure=DEPARTURE,
            load_lb=load_lb,
            interval_miles=interval,
            origin_place=factories.ORIGIN,
            destination_place=factories.DESTINATION,
        )


class CheckpointTests(SimpleTestCase):
    def test_checkpoints_are_spaced_at_the_requested_interval(self):
        route = factories.make_route("Route A", distance_miles=100, duration_hours=2)
        for interval in (10, 25, 50):
            with self.subTest(interval=interval):
                plan = run_plan([route], factories.CALM, interval=interval)
                checkpoints = plan.routes[0].checkpoints
                gaps = [
                    b.distance_miles - a.distance_miles
                    for a, b in zip(checkpoints, checkpoints[1:-1])
                ]
                for gap in gaps:
                    self.assertAlmostEqual(gap, interval, places=5)

    def test_first_checkpoint_is_the_origin_and_last_is_the_destination(self):
        route = factories.make_route("Route A", distance_miles=100, duration_hours=2)
        plan = run_plan([route], factories.CALM)
        checkpoints = plan.routes[0].checkpoints
        self.assertEqual(checkpoints[0].distance_miles, 0.0)
        self.assertAlmostEqual(checkpoints[-1].lat, route.points[-1][0], places=5)
        self.assertAlmostEqual(checkpoints[-1].lon, route.points[-1][1], places=5)

    def test_eta_advances_and_arrival_matches_the_route_duration(self):
        route = factories.make_route("Route A", distance_miles=100, duration_hours=4)
        plan = run_plan([route], factories.CALM)
        checkpoints = plan.routes[0].checkpoints
        self.assertEqual(checkpoints[0].eta, DEPARTURE)
        for earlier, later in zip(checkpoints, checkpoints[1:]):
            self.assertLess(earlier.eta, later.eta)
        self.assertAlmostEqual(
            (checkpoints[-1].eta - DEPARTURE).total_seconds() / 3600, 4.0, delta=0.05
        )

    def test_segment_miles_cover_the_whole_route(self):
        route = factories.make_route("Route A", distance_miles=100, duration_hours=2)
        plan = run_plan([route], factories.CALM)
        covered = sum(c.segment_miles for c in plan.routes[0].checkpoints)
        total = plan.routes[0].checkpoints[-1].distance_miles
        self.assertAlmostEqual(covered, total, places=3)

    def test_weather_is_sampled_at_each_checkpoint_eta(self):
        """A storm that only exists in hour 3 must appear on hour-3 checkpoints."""
        route = factories.make_route("Route A", distance_miles=400, duration_hours=8)
        stormy_hour_three = factories.forecast_factory(
            lambda lat, lon, hour: {"wind": 60.0 if hour == 3 else 5.0}
        )
        plan = run_plan([route], stormy_hour_three)
        blocked = [c for c in plan.routes[0].checkpoints if c.risk.level is RiskLevel.NO_TRAVEL]
        self.assertTrue(blocked, "expected the hour-3 storm to block some checkpoints")
        for checkpoint in blocked:
            self.assertEqual((checkpoint.eta - DEPARTURE).total_seconds() // 3600, 3)


class ScoringTests(SimpleTestCase):
    def test_risk_miles_add_up_to_the_route_distance(self):
        route = factories.make_route("Route A", distance_miles=200, duration_hours=4)
        plan = run_plan([route], factories.CALM)
        scored = plan.routes[0]
        bucket_total = (
            scored.no_travel_miles + scored.severe_miles + scored.high_miles
            + scored.moderate_miles + scored.low_miles
        )
        self.assertAlmostEqual(bucket_total, scored.checkpoints[-1].distance_miles, places=3)

    def test_calm_weather_scores_low(self):
        plan = run_plan([factories.make_route("Route A", distance_miles=200, duration_hours=4)], factories.CALM)
        scored = plan.routes[0]
        self.assertEqual(scored.average_risk, 0.0)
        self.assertIs(scored.worst_level, RiskLevel.LOW)
        self.assertEqual(scored.warnings, [])

    def test_load_escalation_reaches_the_route_score(self):
        route = factories.make_route("Route A", distance_miles=200, duration_hours=4)
        windy = factories.forecast_factory(lambda lat, lon, hour: {"wind": 38.0})
        light = run_plan([route], windy, load_lb=10_000)
        heavy = run_plan([route], windy, load_lb=45_000)
        self.assertIs(light.routes[0].worst_level, RiskLevel.HIGH)
        self.assertIs(heavy.routes[0].worst_level, RiskLevel.SEVERE)
        self.assertGreater(heavy.routes[0].severe_miles, 0)


class RecommendationTests(SimpleTestCase):
    """The stated order: fewest Severe, fewest High, lowest average, shortest time."""

    def _north_is_bad(self, threshold: float, wind: float):
        return factories.forecast_factory(
            lambda lat, lon, hour: {"wind": wind if lat > threshold else 5.0}
        )

    def test_fewest_severe_miles_wins_over_a_faster_route(self):
        fast_but_severe = factories.make_route("Route A", distance_miles=400, duration_hours=6, lat_offset=1.0)
        slow_but_calm = factories.make_route("Route B", distance_miles=460, duration_hours=9)
        plan = run_plan([fast_but_severe, slow_but_calm], self._north_is_bad(41.0, 48.0))

        best = plan.routes[0]
        self.assertTrue(best.is_recommended)
        self.assertEqual(best.geometry.name, "Route B")
        self.assertEqual(best.severe_miles, 0.0)
        self.assertGreater(plan.routes[1].severe_miles, 0.0)

    def test_high_miles_break_a_severe_tie(self):
        windy_a = factories.make_route("Route A", distance_miles=400, duration_hours=6, lat_offset=1.0)
        calm_b = factories.make_route("Route B", distance_miles=400, duration_hours=6)
        plan = run_plan([windy_a, calm_b], self._north_is_bad(41.0, 38.0))
        self.assertEqual(plan.routes[0].geometry.name, "Route B")
        self.assertEqual(plan.routes[0].severe_miles, plan.routes[1].severe_miles)
        self.assertLess(plan.routes[0].high_miles, plan.routes[1].high_miles)

    def test_shortest_travel_time_breaks_an_otherwise_equal_tie(self):
        slow = factories.make_route("Route A", distance_miles=400, duration_hours=9)
        quick = factories.make_route("Route B", distance_miles=400, duration_hours=6)
        plan = run_plan([slow, quick], factories.CALM)
        self.assertEqual(plan.routes[0].geometry.name, "Route B")
        self.assertEqual([r.rank for r in plan.routes], [1, 2])

    def test_no_travel_miles_outrank_every_other_criterion(self):
        blocked_but_fast = factories.make_route("Route A", distance_miles=380, duration_hours=5, lat_offset=1.0)
        clear_but_slow = factories.make_route("Route B", distance_miles=500, duration_hours=11)
        plan = run_plan([blocked_but_fast, clear_but_slow], self._north_is_bad(41.0, 60.0))
        self.assertEqual(plan.routes[0].geometry.name, "Route B")
        self.assertGreater(plan.routes[1].no_travel_miles, 0)
        self.assertIn("No Travel", " ".join(plan.routes[1].warnings))

    def test_exactly_one_route_is_recommended_and_ranks_are_sequential(self):
        routes = [
            factories.make_route("Route A", distance_miles=400, duration_hours=8),
            factories.make_route("Route B", distance_miles=410, duration_hours=7),
            factories.make_route("Route C", distance_miles=430, duration_hours=9),
        ]
        plan = run_plan(routes, factories.CALM)
        self.assertEqual(sum(r.is_recommended for r in plan.routes), 1)
        self.assertEqual([r.rank for r in plan.routes], [1, 2, 3])
        self.assertEqual(plan.routes[0].geometry.name, "Route B")


class HeatmapTests(SimpleTestCase):
    def test_grid_covers_48_hours_for_every_corridor_point(self):
        routes = [factories.make_route("Route A", distance_miles=400, duration_hours=8)]
        plan = run_plan(routes, factories.CALM)
        heatmap = plan.heatmap

        self.assertEqual(len(heatmap["hours"]), HEATMAP_HOURS)
        self.assertTrue(heatmap["points"])
        for key in ("risk", "wind_mph", "rain_in_hr", "snow_in_hr"):
            self.assertEqual(len(heatmap[key]), len(heatmap["points"]), key)
            for row in heatmap[key]:
                self.assertEqual(len(row), HEATMAP_HOURS, key)

    def test_anchor_is_the_departure_hour(self):
        plan = run_plan([factories.make_route("Route A", distance_miles=200, duration_hours=4)], factories.CALM)
        self.assertEqual(plan.heatmap["anchor"], DEPARTURE.isoformat())
        self.assertEqual(
            plan.heatmap["hours"][-1], (DEPARTURE + timedelta(hours=HEATMAP_HOURS - 1)).isoformat()
        )

    def test_risk_scores_track_the_weather(self):
        stormy = factories.forecast_factory(lambda lat, lon, hour: {"snow": 4.0})
        plan = run_plan([factories.make_route("Route A", distance_miles=200, duration_hours=4)], stormy)
        self.assertTrue(all(cell == int(RiskLevel.NO_TRAVEL) for row in plan.heatmap["risk"] for cell in row))
