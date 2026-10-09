from django.test import SimpleTestCase

from routing.services.geo import (
    cumulative_miles,
    decode_polyline,
    haversine_miles,
    point_at_distance,
    sample_every,
)

# Roughly 1 degree of latitude per 69 miles, due north from the equator.
NORTH_LINE = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)]


class DistanceTests(SimpleTestCase):
    def test_known_distance(self):
        # New York to Philadelphia is about 80 miles.
        miles = haversine_miles((40.7128, -74.0060), (39.9526, -75.1652))
        self.assertAlmostEqual(miles, 80.5, delta=1.5)

    def test_zero_distance(self):
        self.assertEqual(haversine_miles((10.0, 10.0), (10.0, 10.0)), 0.0)

    def test_cumulative_is_monotonic(self):
        cumulative = cumulative_miles(NORTH_LINE)
        self.assertEqual(cumulative[0], 0.0)
        self.assertLess(cumulative[0], cumulative[1])
        self.assertLess(cumulative[1], cumulative[2])


class SamplingTests(SimpleTestCase):
    def test_interpolates_within_a_segment(self):
        cumulative = cumulative_miles(NORTH_LINE)
        midpoint = point_at_distance(NORTH_LINE, cumulative, cumulative[-1] / 2)
        self.assertAlmostEqual(midpoint[0], 1.0, places=3)

    def test_clamps_outside_the_line(self):
        cumulative = cumulative_miles(NORTH_LINE)
        self.assertEqual(point_at_distance(NORTH_LINE, cumulative, -5), NORTH_LINE[0])
        self.assertEqual(point_at_distance(NORTH_LINE, cumulative, 99_999), NORTH_LINE[-1])

    def test_spacing_matches_the_interval(self):
        samples = sample_every(NORTH_LINE, 10.0)
        self.assertEqual(samples[0].distance_miles, 0.0)
        for earlier, later in zip(samples, samples[1:-1]):
            self.assertAlmostEqual(later.distance_miles - earlier.distance_miles, 10.0, places=6)

    def test_last_sample_is_the_destination(self):
        samples = sample_every(NORTH_LINE, 10.0)
        total = cumulative_miles(NORTH_LINE)[-1]
        self.assertAlmostEqual(samples[-1].distance_miles, total, places=6)
        self.assertEqual((samples[-1].lat, samples[-1].lon), NORTH_LINE[-1])

    def test_indices_are_sequential(self):
        samples = sample_every(NORTH_LINE, 25.0)
        self.assertEqual([s.index for s in samples], list(range(len(samples))))

    def test_rejects_a_non_positive_interval(self):
        with self.assertRaises(ValueError):
            sample_every(NORTH_LINE, 0)

    def test_empty_line(self):
        self.assertEqual(sample_every([], 10.0), [])


class PolylineTests(SimpleTestCase):
    def test_decodes_the_reference_example(self):
        # The example from Google's encoded-polyline specification.
        self.assertEqual(
            [(round(lat, 5), round(lon, 5)) for lat, lon in decode_polyline("_p~iF~ps|U_ulLnnqC_mqNvxq`@")],
            [(38.5, -120.2), (40.7, -120.95), (43.252, -126.453)],
        )
