"""Live smoke test: one real pass against Nominatim, OSRM, and Open-Meteo.

These are free, no-key public APIs. The test does 3 real requests total
(plus the module's own 1 req/s throttle keeps us polite). If any API is
down, the failure message says which one — that's signal, not noise.
"""

import os
import sys
import unittest
import urllib.request
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from way2 import geo


class TestLiveAPIs(unittest.TestCase):
    def test_live_geocode(self):
        g = geo.geocode("Cherry Hill, NJ")
        self.assertIn("lat", g)
        # Cherry Hill NJ is roughly 39.9, -75.0 — sanity, not precision.
        self.assertTrue(39.5 < g["lat"] < 40.3, g)
        self.assertTrue(-75.5 < g["lon"] < -74.5, g)
        print(f"\n  geocode -> {g['label']} ({g['lat']:.4f}, {g['lon']:.4f})")

    def test_live_route(self):
        start = geo.geocode("Cherry Hill, NJ")
        end = geo.geocode("Philadelphia, PA")
        r = geo.route([(start["lat"], start["lon"]), (end["lat"], end["lon"])])
        # ~10 miles; allow wide bounds in case of detours.
        self.assertTrue(5_000 < r["distance_m"] < 60_000, r["distance_m"])
        self.assertTrue(len(r["steps"]) > 3, "expected turn-by-turn steps")
        print(f"\n  route -> {geo.format_distance(r['distance_m'])}, "
              f"{geo.format_duration(r['duration_s'])}, "
              f"{len(r['steps'])} steps; first: {r['steps'][0]['instruction']}")

    def test_live_find_places(self):
        # Bars in Philadelphia are plentiful — a reliable live check that
        # the Nominatim viewbox query works end to end.
        places = geo.find_places(39.9526, -75.1652, "nightlife")
        self.assertTrue(len(places) > 0, "expected at least one bar")
        print(f"\n  find_places(nightlife) -> {places[0]['name']}")

    def test_live_open_meteo(self):
        url = ("https://api.open-meteo.com/v1/forecast?latitude=39.93&"
               "longitude=-75.02&current=temperature_2m,weather_code&"
               "timezone=auto")
        req = urllib.request.Request(url, headers={"User-Agent": "GodsEyeView/1.0"})
        with urllib.request.urlopen(req, timeout=15) as res:
            data = json.loads(res.read())
        self.assertIn("current", data)
        print(f"\n  open-meteo -> {data['current'].get('temperature_2m')}°C now")


if __name__ == "__main__":
    unittest.main()
