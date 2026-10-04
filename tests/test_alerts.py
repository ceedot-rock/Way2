"""Unit tests for faster-route alerts (OSRM alternatives, no live traffic)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from way2 import alerts
from way2.alerts import check_faster_route


class FakeTrip:
    def __init__(self, route):
        self._route = route

    def current_route(self):
        return self._route


def route(duration_s, alternatives="missing"):
    r = {"distance_m": 16093, "duration_s": duration_s, "steps": []}
    if alternatives != "missing":
        r["alternatives"] = alternatives
    return r


def alt(duration_s):
    return {"distance_m": 17000, "duration_s": duration_s, "steps": []}


class TestCheckFasterRoute(unittest.TestCase):
    def test_meaningfully_faster_alerts(self):
        trip = FakeTrip(route(1800, [alt(1200)]))  # saves 10 min
        result = check_faster_route(trip)
        self.assertIsNotNone(result)
        self.assertIn("10", result)
        self.assertIn("faster", result.lower())

    def test_barely_faster_silent(self):
        trip = FakeTrip(route(1800, [alt(1740)]))  # saves 1 min, 3%
        self.assertIsNone(check_faster_route(trip))

    def test_five_minute_rule(self):
        trip = FakeTrip(route(1200, [alt(840)]))  # saves 6 min = 30%
        self.assertIsNotNone(check_faster_route(trip))

    def test_no_alternatives_silent(self):
        trip = FakeTrip(route(1800, []))
        self.assertIsNone(check_faster_route(trip))

    def test_missing_alternatives_field_is_honest(self):
        trip = FakeTrip(route(1800))  # no "alternatives" key at all
        with self.assertRaises(RuntimeError) as ctx:
            check_faster_route(trip)
        self.assertIn("alternative routes", str(ctx.exception).lower())

    def test_slower_alternative_silent(self):
        trip = FakeTrip(route(1800, [alt(2100)]))
        self.assertIsNone(check_faster_route(trip))

    def test_picks_best_alternative(self):
        trip = FakeTrip(route(2400, [alt(2340), alt(1500)]))
        result = check_faster_route(trip)
        self.assertIsNotNone(result)
        self.assertIn("15", result)

    def test_zero_duration_silent(self):
        trip = FakeTrip(route(0, [alt(0)]))
        self.assertIsNone(check_faster_route(trip))


if __name__ == "__main__":
    unittest.main()
