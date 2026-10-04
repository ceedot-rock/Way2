"""Unit tests for way2/trip.py — trip state and the deterministic parser.

Intent vocabulary matches docs/CONTRACT.md exactly.
Run:  python3 -m unittest discover -s tests -v   (from the repo root)
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from way2 import trip
from way2.trip import INTENTS, Trip, parse_command


class FakeGeo:
    """Stand-in for way2.geo: no network. Accepts label waypoints like
    the real geo.route(), which geocodes place names on the fly."""

    def route(self, points):
        legs = max(len(points) - 1, 0)
        return {
            "distance_m": legs * 8046.7,
            "duration_s": legs * 600,
            "distance_mi": round(legs * 8046.7 / 1609.344, 1),
            "duration_min": legs * 10.0,
            "geometry": [(39.9 + i * 0.001, -75.0) for i in range(11)],
            "alternatives": [],
            "steps": [],
        }


def make_trip(**kwargs):
    kwargs.setdefault("geo_mod", FakeGeo())
    return Trip(**kwargs)


class TestParseCommand(unittest.TestCase):
    def test_set_origin(self):
        for text in ["starting from Cherry Hill", "start from home",
                     "I'm at the depot", "my location is Camden"]:
            with self.subTest(text=text):
                result = parse_command(text)
                self.assertEqual(result["intent"], "set_origin")
                self.assertTrue(result["params"].get("origin"))

    def test_set_destination(self):
        result = parse_command("take me to Philadelphia.")
        self.assertEqual(result["intent"], "set_destination")
        self.assertEqual(result["params"]["destination"], "Philadelphia")
        for text in ["navigate to work", "drive to mom's house", "go to Camden"]:
            with self.subTest(text=text):
                self.assertEqual(parse_command(text)["intent"], "set_destination")

    def test_add_stop(self):
        result = parse_command("add a stop at the gas station")
        self.assertEqual(result["intent"], "add_stop")
        self.assertEqual(result["params"]["stop"], "the gas station")

    def test_skip_next(self):
        for text in ["skip the next stop", "skip next stop", "skip stop"]:
            with self.subTest(text=text):
                self.assertEqual(parse_command(text)["intent"], "skip_next")

    def test_eta(self):
        for text in ["what's my ETA", "ETA?", "when will I arrive",
                     "how long until we get there"]:
            with self.subTest(text=text):
                self.assertEqual(parse_command(text)["intent"], "eta")

    def test_summary(self):
        for text in ["trip summary", "summarize my trip", "summary"]:
            with self.subTest(text=text):
                self.assertEqual(parse_command(text)["intent"], "summary")

    def test_find_places(self):
        result = parse_command("find scenic spots near Camden")
        self.assertEqual(result["intent"], "find_places")
        self.assertEqual(result["params"]["category"], "scenic")
        self.assertEqual(result["params"]["near"], "Camden")

    def test_lunch_maps_to_food(self):
        for text in ["plan lunch along the route", "I'm hungry",
                     "find restaurants", "where can I eat"]:
            with self.subTest(text=text):
                result = parse_command(text)
                self.assertEqual(result["intent"], "find_places")
                self.assertEqual(result["params"]["category"], "food")

    def test_weather(self):
        for text in ["weather along the route", "weather on my route",
                     "will it rain", "storms ahead"]:
            with self.subTest(text=text):
                self.assertEqual(parse_command(text)["intent"], "weather")

    def test_faster_route(self):
        for text in ["any faster route", "is there a quicker way", "reroute"]:
            with self.subTest(text=text):
                self.assertEqual(parse_command(text)["intent"], "faster_route")

    def test_help_and_quit(self):
        self.assertEqual(parse_command("help")["intent"], "help")
        for text in ["quit", "exit", "bye"]:
            with self.subTest(text=text):
                self.assertEqual(parse_command(text)["intent"], "quit")

    def test_unknown(self):
        result = parse_command("tell me a joke about trucks")
        self.assertEqual(result["intent"], "unknown")
        self.assertEqual(result["params"]["text"], "tell me a joke about trucks")

    def test_empty_is_unknown(self):
        self.assertEqual(parse_command("")["intent"], "unknown")

    def test_intent_names_stable(self):
        self.assertEqual(
            set(INTENTS),
            {"set_origin", "set_destination", "add_stop", "skip_next", "eta",
             "summary", "find_places", "weather", "faster_route", "traffic",
             "help", "quit", "unknown"},
        )

    def test_traffic_intent(self):
        for text in ("traffic on my route", "how's traffic",
                     "any traffic ahead", "traffic report"):
            self.assertEqual(parse_command(text)["intent"], "traffic",
                             f"missed: {text!r}")

    def test_faster_route_still_wins_over_traffic(self):
        self.assertEqual(parse_command("any faster route")["intent"],
                         "faster_route")


class TestTrip(unittest.TestCase):
    def setUp(self):
        self.trip = make_trip()
        self.trip.set_origin("Cherry Hill")
        self.trip.add_stop("Philadelphia")

    def test_waypoints(self):
        self.assertEqual(self.trip.waypoints, ["Cherry Hill", "Philadelphia"])

    def test_add_stop_returns_none(self):
        self.assertIsNone(self.trip.add_stop("Camden"))
        self.assertEqual(self.trip.stops, ["Philadelphia", "Camden"])

    def test_add_stop_rejects_blank(self):
        with self.assertRaises(ValueError):
            self.trip.add_stop("   ")

    def test_skip_next_removes_last_added(self):
        self.trip.add_stop("Camden")
        self.assertEqual(self.trip.skip_next(), "Camden")
        self.assertEqual(self.trip.stops, ["Philadelphia"])

    def test_skip_next_protects_destination(self):
        # Only the destination left -> nothing skippable.
        with self.assertRaises(ValueError) as ctx:
            self.trip.skip_next()
        self.assertIn("no upcoming stops", str(ctx.exception).lower())

    def test_set_origin(self):
        self.trip.set_origin("Camden")
        self.assertEqual(self.trip.origin_label, "Camden")

    def test_current_route_cached(self):
        first = self.trip.current_route()
        self.assertEqual(first["duration_min"], 10.0)
        self.trip.add_stop("Camden")
        second = self.trip.current_route()
        self.assertIsNot(first, second)
        self.assertEqual(second["duration_min"], 20.0)

    def test_midpoint(self):
        lat, lon = self.trip.midpoint()
        self.assertAlmostEqual(lat, 39.9 + 5 * 0.001)
        self.assertAlmostEqual(lon, -75.0)

    def test_eta_mentions_minutes(self):
        eta = self.trip.eta()
        self.assertIn("10", eta)
        self.assertIn("minutes", eta.lower())

    def test_eta_without_destination_is_plain_language(self):
        t = make_trip()
        with self.assertRaises(ValueError) as ctx:
            t.eta()
        self.assertIn("navigate", str(ctx.exception).lower())

    def test_summary(self):
        summary = self.trip.summary()
        self.assertIn("Cherry Hill", summary)
        self.assertIn("Philadelphia", summary)
        self.assertIn("10", summary)
        self.assertIn("5.0 miles", summary)

    def test_summary_without_stops_is_plain_language(self):
        t = make_trip()
        self.assertIn("No trip planned", t.summary())


if __name__ == "__main__":
    unittest.main()
