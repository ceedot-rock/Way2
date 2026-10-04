"""Unit tests for way2/app.py — real partner modules, faked geo/weather HTTP.

Run from the repo root:  python3 -m unittest discover -s tests -v
"""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from way2 import geo, trip, weather, alerts
from way2.app import Driver
from way2.geo import GeoError


def _fake_geocode(address):
    known = {
        "cherry hill": (39.9259, -75.0243, "Cherry Hill"),
        "philadelphia": (39.9526, -75.1652, "Philadelphia"),
        "camden": (39.9256, -75.1196, "Camden"),
    }
    hit = known.get(address.lower())
    if not hit:
        raise GeoError(f"Couldn't find '{address}'.")
    lat, lon, label = hit
    return {"lat": lat, "lon": lon, "label": label}


def _fake_route(points):
    return {
        "distance_m": 16093, "duration_s": 1200,
        "distance_mi": 10.0, "duration_min": 20.0,
        "geometry": [(39.9, -75.0)] * 11,
        "alternatives": [],
        "steps": [],
    }


def _calm_weather(lat, lon):
    return {"weather_code": 0, "wind_speed_10m": 5,
            "temperature_2m": 20, "precipitation": 0}


def _stormy_weather(lat, lon):
    return {"weather_code": 95, "wind_speed_10m": 55,
            "temperature_2m": 22, "precipitation": 3}


class TestDriver(unittest.TestCase):
    def setUp(self):
        self.patches = [
            patch.object(geo, "geocode", _fake_geocode),
            patch.object(geo, "route", _fake_route),
            patch.object(geo, "find_places",
                         lambda lat, lon, cat: [{"name": "Cooper River Park",
                                                 "lat": lat, "lon": lon,
                                                 "address": "Cooper River Park, NJ"}]),
            patch.object(weather, "fetch_current", _calm_weather),
        ]
        for p in self.patches:
            p.start()
        self.d = Driver(trip, weather, alerts)

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_set_origin_then_navigate(self):
        r = self.d.handle("starting from Cherry Hill")
        self.assertIn("Cherry Hill", r)
        self.assertTrue(self.d.origin_set)
        r = self.d.handle("navigate to Philadelphia")
        self.assertIn("Destination set: Philadelphia", r)
        self.assertIn("10.0 miles", r)
        self.assertIn("20 minutes", r)

    def test_navigate_before_origin_asks_for_it(self):
        r = self.d.handle("navigate to Philadelphia")
        self.assertIn("starting from", r)

    def test_navigate_unknown_place(self):
        self.d.handle("starting from Cherry Hill")
        r = self.d.handle("navigate to Asdfghjkl")
        self.assertIn("Couldn't find", r)

    def test_add_stop_and_skip(self):
        self.d.handle("starting from Cherry Hill")
        self.d.handle("navigate to Philadelphia")
        r = self.d.handle("add a stop in Camden")
        self.assertIn("Camden", r)
        # skip_next drops the most recently added stop; the destination
        # (first stop) is never skipped.
        r = self.d.handle("skip the next stop")
        self.assertIn("Skipped Camden", r)
        self.assertEqual(self.d.trip.stops, ["Philadelphia"])

    def test_skip_with_no_stops(self):
        self.d.handle("starting from Cherry Hill")
        r = self.d.handle("skip the next stop")
        self.assertIn("no upcoming stops", r)

    def test_eta(self):
        self.d.handle("starting from Cherry Hill")
        self.d.handle("navigate to Philadelphia")
        r = self.d.handle("what's my ETA")
        self.assertIn("20", r)
        self.assertIn("minut", r.lower())

    def test_eta_with_no_trip(self):
        r = self.d.handle("what's my ETA")
        self.assertIn("starting from", r)

    def test_find_places_scenic(self):
        self.d.handle("starting from Cherry Hill")
        r = self.d.handle("find scenic spots")
        self.assertIn("Cooper River Park", r)
        self.assertIn("Cherry Hill", r)

    def test_find_places_near_named_place(self):
        self.d.handle("starting from Cherry Hill")
        r = self.d.handle("find nightlife near Philadelphia")
        self.assertIn("Philadelphia", r)

    def test_lunch_alias_finds_food(self):
        self.d.handle("starting from Cherry Hill")
        self.d.handle("navigate to Philadelphia")
        r = self.d.handle("find restaurants")
        self.assertIn("Cooper River Park", r)

    def test_summary(self):
        self.d.handle("starting from Cherry Hill")
        self.d.handle("navigate to Philadelphia")
        r = self.d.handle("trip summary")
        self.assertIn("Philadelphia", r)
        self.assertIn("20", r)

    def test_summary_empty_trip(self):
        r = self.d.handle("trip summary")
        self.assertIn("No trip planned", r)

    def test_summary_includes_storm_alert(self):
        self.patches[-1].stop()  # swap calm -> stormy
        self.patches[-1] = patch.object(weather, "fetch_current", _stormy_weather)
        self.patches[-1].start()
        self.d.handle("starting from Cherry Hill")
        self.d.handle("navigate to Philadelphia")
        r = self.d.handle("trip summary")
        self.assertIn("Thunderstorm", r)

    def test_faster_route_none(self):
        self.d.handle("starting from Cherry Hill")
        self.d.handle("navigate to Philadelphia")
        r = self.d.handle("any faster route")
        self.assertIn("fastest route", r)

    def test_faster_route_found(self):
        def _route_with_alt(points):
            r = _fake_route(points)
            r["duration_s"] = 1800
            r["duration_min"] = 30.0
            r["alternatives"] = [{"duration_min": 20.0, "distance_mi": 9.0}]
            return r
        with patch.object(geo, "route", _route_with_alt):
            d2 = Driver(trip, weather, alerts)
            d2.handle("starting from Cherry Hill")
            d2.handle("navigate to Philadelphia")
            r = d2.handle("any faster route")
        self.assertIn("faster way", r)
        self.assertIn("10 minutes", r)

    def test_weather_clear(self):
        self.d.handle("starting from Cherry Hill")
        self.d.handle("navigate to Philadelphia")
        r = self.d.handle("weather along the route")
        self.assertIn("Clear driving", r)

    def test_traffic_without_key_says_so_plainly(self):
        self.d.handle("starting from Cherry Hill")
        self.d.handle("navigate to Philadelphia")
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TOMTOM_API_KEY", None)
            r = self.d.handle("traffic on my route")
        self.assertIn("TOMTOM_API_KEY", r)

    def test_traffic_with_key_reports_headline_and_incidents(self):
        from way2 import traffic as traffic_mod
        report = {
            "segments": [],
            "incidents": [{"category": "Jam",
                           "description": "Congestion on I-676 W"}],
            "summary": {"headline": "Heavy traffic on 2 of 5 segments",
                        "total_delay_sec": 300},
        }
        self.d.handle("starting from Cherry Hill")
        self.d.handle("navigate to Philadelphia")
        with patch.object(traffic_mod, "get_traffic_for_route",
                          return_value=report), \
             patch.dict(os.environ, {"TOMTOM_API_KEY": "fake"}):
            r = self.d.handle("traffic on my route")
        self.assertIn("Heavy traffic", r)
        self.assertIn("I-676", r)

    def test_faster_route_notes_missing_traffic_key(self):
        self.d.handle("starting from Cherry Hill")
        self.d.handle("navigate to Philadelphia")
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TOMTOM_API_KEY", None)
            r = self.d.handle("any faster route")
        self.assertIn("TOMTOM_API_KEY", r)

    def test_faster_route_appends_live_traffic_note(self):
        from way2 import traffic as traffic_mod
        report = {
            "segments": [],
            "incidents": [],
            "summary": {"headline": "Flowing freely",
                        "total_delay_sec": 240},
        }
        self.d.handle("starting from Cherry Hill")
        self.d.handle("navigate to Philadelphia")
        with patch.object(traffic_mod, "get_traffic_for_route",
                          return_value=report), \
             patch.dict(os.environ, {"TOMTOM_API_KEY": "fake"}):
            r = self.d.handle("any faster route")
        self.assertIn("Live traffic", r)

    def test_unknown_command_gets_help(self):
        r = self.d.handle("tell me a joke")
        self.assertIn("navigate to", r)

    def test_quit_returns_none(self):
        self.assertIsNone(self.d.handle("quit"))

    def test_help(self):
        r = self.d.handle("help")
        self.assertIn("navigate to", r)


if __name__ == "__main__":
    unittest.main()
