"""Unit tests for way2/geo.py — HTTP is mocked; no network needed.

Run:  python3 -m unittest discover -s tests -v
"""

import json
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from way2 import geo
from way2.geo import GeoError


def _resp(obj):
    return json.dumps(obj).encode()


class TestGeocode(unittest.TestCase):
    @patch("way2.geo._throttled_get")
    def test_geocode_ok(self, mock_get):
        mock_get.return_value = _resp([{
            "lat": "39.9259", "lon": "-75.0243",
            "display_name": "Cherry Hill, Camden County, New Jersey, USA",
        }])
        g = geo.geocode("Cherry Hill NJ")
        self.assertAlmostEqual(g["lat"], 39.9259)
        self.assertAlmostEqual(g["lon"], -75.0243)
        self.assertEqual(g["label"], "Cherry Hill")

    @patch("way2.geo._throttled_get")
    def test_geocode_not_found(self, mock_get):
        mock_get.return_value = _resp([])
        with self.assertRaises(GeoError) as ctx:
            geo.geocode("asdfghjkl nowhere")
        self.assertIn("Couldn't find", str(ctx.exception))

    def test_geocode_empty(self):
        with self.assertRaises(GeoError):
            geo.geocode("   ")

    @patch("way2.geo._throttled_get")
    def test_geocode_network_failure_is_geoerror(self, mock_get):
        mock_get.side_effect = GeoError("Couldn't reach the map service: boom")
        with self.assertRaises(GeoError):
            geo.geocode("Philadelphia")


class TestRoute(unittest.TestCase):
    OSRM_OK = {
        "code": "Ok",
        "routes": [{
            "distance": 15413.4, "duration": 1257.4,
            "geometry": {"coordinates": [[-75.0, 39.9], [-75.1, 39.92],
                                         [-75.16, 39.95]]},
            "legs": [{"steps": [
                {"distance": 500, "duration": 60, "name": "Main St",
                 "maneuver": {"type": "depart", "modifier": ""}},
                {"distance": 14913.4, "duration": 1197.4, "name": "I-95",
                 "maneuver": {"type": "turn", "modifier": "left"}},
                {"distance": 0, "duration": 0, "name": "",
                 "maneuver": {"type": "arrive", "modifier": ""}},
            ]}],
        }, {
            "distance": 16000.0, "duration": 1100.0,
            "geometry": {"coordinates": []},
            "legs": [],
        }],
    }

    @patch("way2.geo._throttled_get")
    def test_route_ok(self, mock_get):
        mock_get.return_value = _resp(self.OSRM_OK)
        r = geo.route([(39.9, -75.0), (39.95, -75.16)])
        self.assertEqual(r["distance_m"], 15413)
        self.assertEqual(r["duration_s"], 1257)
        self.assertEqual(len(r["steps"]), 3)
        self.assertIn("Main St", r["steps"][0]["instruction"])
        self.assertTrue(r["steps"][1]["instruction"].startswith("Turn left"))
        self.assertEqual(r["steps"][2]["instruction"],
                         "Arrive at your destination")
        # partner-facing keys (computed from the rounded duration_s)
        self.assertAlmostEqual(r["duration_min"], round(1257 / 60, 1), places=1)
        self.assertAlmostEqual(r["distance_mi"], 15413.4 / 1609.344, places=1)
        self.assertEqual(r["geometry"],
                         [(39.9, -75.0), (39.92, -75.1), (39.95, -75.16)])
        self.assertEqual(len(r["alternatives"]), 1)
        self.assertAlmostEqual(r["alternatives"][0]["duration_min"],
                               1100.0 / 60, places=1)

    @patch("way2.geo._throttled_get")
    def test_route_accepts_place_names(self, mock_get):
        # string waypoints are geocoded via Nominatim first
        mock_get.side_effect = [
            _resp([{"lat": "39.9", "lon": "-75.0",
                    "display_name": "Cherry Hill, NJ, USA"}]),
            _resp([{"lat": "39.95", "lon": "-75.16",
                    "display_name": "Philadelphia, PA, USA"}]),
            _resp(self.OSRM_OK),
        ]
        r = geo.route(["Cherry Hill", "Philadelphia"])
        self.assertEqual(r["distance_m"], 15413)
        self.assertEqual(mock_get.call_count, 3)

    def test_route_needs_two_points(self):
        with self.assertRaises(GeoError):
            geo.route([(39.9, -75.0)])

    @patch("way2.geo._throttled_get")
    def test_route_no_route(self, mock_get):
        mock_get.return_value = _resp({"code": "NoRoute", "routes": []})
        with self.assertRaises(GeoError) as ctx:
            geo.route([(0, 0), (1, 1)])
        self.assertIn("Couldn't find a driving route", str(ctx.exception))

    def test_format_helpers(self):
        self.assertEqual(geo.format_distance(16093.44), "10.0 miles")
        self.assertEqual(geo.format_duration(3660), "1 hr 1 min")
        self.assertEqual(geo.format_duration(600), "10 min")


class TestFindPlaces(unittest.TestCase):
    @patch("way2.geo._throttled_get")
    def test_find_places_ok(self, mock_get):
        mock_get.return_value = _resp([
            {"lat": "39.9", "lon": "-75.0",
             "display_name": "Cooper River Park, Pennsauken, NJ, USA"},
            {"lat": "39.91", "lon": "-75.01",
             "display_name": "Cherry Hill Mall, Cherry Hill, NJ, USA"},
        ])
        places = geo.find_places(39.9, -75.0, "scenic")
        self.assertEqual(len(places), 2)
        self.assertEqual(places[0]["name"], "Cooper River Park")
        self.assertAlmostEqual(places[0]["lat"], 39.9)

    def test_find_places_bad_category(self):
        with self.assertRaises(GeoError) as ctx:
            geo.find_places(39.9, -75.0, "tacos")
        self.assertIn("scenic", str(ctx.exception))

    @patch("way2.geo._throttled_get")
    def test_find_places_none_found(self, mock_get):
        mock_get.return_value = _resp([])
        self.assertEqual(geo.find_places(0, 0, "shows"), [])


if __name__ == "__main__":
    unittest.main()
