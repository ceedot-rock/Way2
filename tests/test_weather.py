"""Unit tests for Open-Meteo weather alerts. HTTP is mocked; one live
smoke test lives in tools/smoke_weather.py (run separately, not in CI)."""
import io
import os
import sys
import json
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from way2 import weather
from way2.weather import (
    alerts_along_route,
    alerts_for_point,
    fetch_current,
    sample_points,
)



def fake_urlopen(payload):
    class FakeResponse:
        def __init__(self, data):
            self._data = json.dumps(data).encode()

        def read(self):
            return self._data

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    return FakeResponse(payload)


def current(code=0, temp=20.0, wind=10.0, precip=0.0):
    return {
        "current": {
            "temperature_2m": temp,
            "precipitation": precip,
            "weather_code": code,
            "wind_speed_10m": wind,
        }
    }


class TestAlertsForPoint(unittest.TestCase):
    def test_clear_sky_no_alerts(self):
        self.assertEqual(alerts_for_point("along the way", current(0)["current"]), [])

    def test_thunderstorm(self):
        alerts = alerts_for_point("along the way", current(95)["current"])
        self.assertTrue(any("Thunderstorm" in a for a in alerts))

    def test_heavy_rain(self):
        alerts = alerts_for_point("along the way", current(65)["current"])
        self.assertTrue(any("Heavy rain" in a for a in alerts))

    def test_light_rain(self):
        alerts = alerts_for_point("along the way", current(61)["current"])
        self.assertTrue(any("Light rain" in a for a in alerts))

    def test_snow(self):
        alerts = alerts_for_point("along the way", current(73)["current"])
        self.assertTrue(any("Snow" in a for a in alerts))

    def test_fog(self):
        alerts = alerts_for_point("along the way", current(45)["current"])
        self.assertTrue(any("Fog" in a for a in alerts))

    def test_high_wind(self):
        alerts = alerts_for_point("along the way", current(0, wind=55.0)["current"])
        self.assertTrue(any("wind" in a.lower() for a in alerts))

    def test_calm_wind_no_alert(self):
        self.assertEqual(alerts_for_point("x", current(0, wind=10.0)["current"]), [])

    def test_extreme_heat(self):
        alerts = alerts_for_point("along the way", current(0, temp=40.0)["current"])
        self.assertTrue(any("heat" in a.lower() for a in alerts))

    def test_extreme_cold(self):
        alerts = alerts_for_point("along the way", current(0, temp=-15.0)["current"])
        self.assertTrue(any("cold" in a.lower() for a in alerts))

    def test_label_included(self):
        alerts = alerts_for_point("near your destination", current(95)["current"])
        self.assertTrue(all("near your destination" in a for a in alerts))


class TestSamplePoints(unittest.TestCase):
    def test_evenly_spaced(self):
        route = {"geometry": [(float(i), 0.0) for i in range(11)]}
        points = sample_points(route, n=3)
        self.assertEqual(points, [(0.0, 0.0), (5.0, 0.0), (10.0, 0.0)])

    def test_short_geometry_returned_whole(self):
        route = {"geometry": [(1.0, 2.0)]}
        self.assertEqual(sample_points(route, n=5), [(1.0, 2.0)])

    def test_empty_geometry(self):
        self.assertEqual(sample_points({"geometry": []}), [])


class TestAlertsAlongRoute(unittest.TestCase):
    def _route(self):
        return {"geometry": [(39.9 + i * 0.01, -75.0) for i in range(21)]}

    def test_rain_somewhere_alerts(self):
        payloads = [current(0), current(0), current(63), current(0), current(0)]
        with patch.object(weather.urllib.request, "urlopen",
                          side_effect=[fake_urlopen(p) for p in payloads]):
            alerts = alerts_along_route(self._route())
        self.assertEqual(len(alerts), 1)
        self.assertIn("rain", alerts[0].lower())

    def test_all_clear_no_alerts(self):
        with patch.object(weather.urllib.request, "urlopen",
                          return_value=fake_urlopen(current(1))):
            self.assertEqual(alerts_along_route(self._route()), [])

    def test_service_failure_degrades_to_empty(self):
        with patch.object(weather.urllib.request, "urlopen",
                          side_effect=Exception("network down")):
            self.assertEqual(alerts_along_route(self._route()), [])

    def test_duplicate_alerts_deduped(self):
        with patch.object(weather.urllib.request, "urlopen",
                          return_value=fake_urlopen(current(95))):
            alerts = alerts_along_route(self._route())
        # same storm at every sample point, but reported once per label set
        self.assertLessEqual(len(alerts), 3)

    def test_route_without_geometry_is_honest(self):
        # No shape data -> we must NOT claim "clear driving".
        from way2.weather import WeatherError
        with self.assertRaises(WeatherError) as ctx:
            alerts_along_route({"distance_m": 16093, "duration_s": 1500})
        self.assertIn("shape", str(ctx.exception).lower())


class TestFetchCurrent(unittest.TestCase):
    def test_parses_current_block(self):
        with patch.object(weather.urllib.request, "urlopen",
                          return_value=fake_urlopen(current(80, temp=12.5))):
            data = fetch_current(39.9, -75.0)
        self.assertEqual(data["weather_code"], 80)
        self.assertEqual(data["temperature_2m"], 12.5)

    def test_missing_current_raises(self):
        with patch.object(weather.urllib.request, "urlopen",
                          return_value=fake_urlopen({"hourly": {}})):
            from way2.weather import WeatherError
            with self.assertRaises(WeatherError):
                fetch_current(39.9, -75.0)


if __name__ == "__main__":
    unittest.main()
