"""Unit tests for way2/traffic.py — HTTP is faked; no TomTom key needed.

Run:  python3 -m unittest discover -s tests -v
"""

import io
import json
import os
import sys
import unittest
import urllib.error
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from way2 import traffic
from way2.traffic import TrafficError

FLOW_OK = {
    "flowSegmentData": {
        "frc": "FRC3",
        "currentSpeed": 40,
        "freeFlowSpeed": 80,
        "currentTravelTime": 90,
        "freeFlowTravelTime": 45,
        "confidence": 0.8,
        "roadClosure": False,
    }
}

INCIDENTS_OK = {
    "incidents": [
        {
            "type": "TrafficIncident",
            "geometry": {"type": "Point", "coordinates": [4.8, 52.4]},
            "properties": {
                "id": "abc123",
                "iconCategory": 6,
                "magnitudeOfDelay": 2,
                "delay": 300,
                "length": 1200,
                "events": [{"description": "Stationary traffic on A10"}],
            },
        }
    ]
}


class _FakeResponse:
    def __init__(self, payload):
        self._payload = json.dumps(payload).encode()

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _fake_urlopen_factory(routes):
    """routes: list of (url_substring, payload_or_exception)."""
    def _fake(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else req
        for needle, payload in routes:
            if needle in url:
                if isinstance(payload, Exception):
                    raise payload
                return _FakeResponse(payload)
        raise AssertionError(f"unexpected URL: {url}")
    return _fake


class TestKeyHandling(unittest.TestCase):
    def test_missing_key_raises_plain_language_error(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TOMTOM_API_KEY", None)
            with self.assertRaises(TrafficError) as ctx:
                traffic.get_traffic_for_route([(52.4, 4.8)])
            self.assertIn("TOMTOM_API_KEY", str(ctx.exception))

    def test_empty_route(self):
        with patch.dict(os.environ, {"TOMTOM_API_KEY": "k"}):
            with self.assertRaises(TrafficError):
                traffic.get_traffic_for_route([])

    def test_key_never_in_error_messages(self):
        with patch.dict(os.environ, {"TOMTOM_API_KEY": "supersecretkey123"}):
            fake = _fake_urlopen_factory([
                ("flowSegmentData", urllib.error.HTTPError(
                    "u", 403, "forbidden", {}, io.BytesIO(b""))),
            ])
            with patch("urllib.request.urlopen", fake):
                try:
                    traffic.flow_at_point(52.4, 4.8)
                except TrafficError as e:
                    self.assertNotIn("supersecretkey123", str(e))
                    return
                self.fail("expected TrafficError")


class TestFlowAtPoint(unittest.TestCase):
    def test_parses_flow_segment(self):
        fake = _fake_urlopen_factory([("flowSegmentData", FLOW_OK)])
        with patch.dict(os.environ, {"TOMTOM_API_KEY": "k"}):
            with patch("urllib.request.urlopen", fake):
                seg = traffic.flow_at_point(52.4, 4.8)
        self.assertEqual(seg["current_speed_kmh"], 40.0)
        self.assertEqual(seg["free_flow_speed_kmh"], 80.0)
        self.assertEqual(seg["delay_sec"], 45)
        self.assertEqual(seg["congestion_pct"], 50.0)
        self.assertFalse(seg["road_closure"])

    def test_no_segment_is_an_error(self):
        fake = _fake_urlopen_factory([("flowSegmentData", {})])
        with patch.dict(os.environ, {"TOMTOM_API_KEY": "k"}):
            with patch("urllib.request.urlopen", fake):
                with self.assertRaises(TrafficError):
                    traffic.flow_at_point(0.0, 0.0)

    def test_403_gives_key_hint(self):
        fake = _fake_urlopen_factory([
            ("flowSegmentData", urllib.error.HTTPError(
                "u", 403, "forbidden", {}, io.BytesIO(b""))),
        ])
        with patch.dict(os.environ, {"TOMTOM_API_KEY": "k"}):
            with patch("urllib.request.urlopen", fake):
                with self.assertRaises(TrafficError) as ctx:
                    traffic.flow_at_point(52.4, 4.8)
                self.assertIn("API key", str(ctx.exception))


class TestIncidents(unittest.TestCase):
    def test_parses_incidents(self):
        fake = _fake_urlopen_factory([("incidentDetails", INCIDENTS_OK)])
        with patch.dict(os.environ, {"TOMTOM_API_KEY": "k"}):
            with patch("urllib.request.urlopen", fake):
                incs = traffic.incidents_along_route([(52.4, 4.8), (52.5, 4.9)])
        self.assertEqual(len(incs), 1)
        self.assertEqual(incs[0]["category"], "Jam")
        self.assertEqual(incs[0]["magnitude"], "Moderate")
        self.assertEqual(incs[0]["delay_sec"], 300)
        self.assertIn("A10", incs[0]["description"])


class TestGetTrafficForRoute(unittest.TestCase):
    def test_full_route(self):
        fake = _fake_urlopen_factory([
            ("flowSegmentData", FLOW_OK),
            ("incidentDetails", INCIDENTS_OK),
        ])
        with patch.dict(os.environ, {"TOMTOM_API_KEY": "k"}):
            with patch("urllib.request.urlopen", fake):
                report = traffic.get_traffic_for_route(
                    [(52.4, 4.8), (52.41, 4.81), (52.42, 4.82)])
        self.assertEqual(len(report["segments"]), 3)
        self.assertEqual(len(report["incidents"]), 1)
        self.assertEqual(report["summary"]["segments_checked"], 3)
        self.assertEqual(report["summary"]["total_delay_sec"], 135)
        self.assertIn("Heavy traffic", report["summary"]["headline"])

    def test_bad_segment_does_not_sink_route(self):
        calls = {"n": 0}

        def flaky(req, timeout=None):
            calls["n"] += 1
            url = req.full_url
            if "flowSegmentData" in url and calls["n"] == 1:
                return _FakeResponse({})
            if "flowSegmentData" in url:
                return _FakeResponse(FLOW_OK)
            return _FakeResponse(INCIDENTS_OK)

        with patch.dict(os.environ, {"TOMTOM_API_KEY": "k"}):
            with patch("urllib.request.urlopen", flaky):
                report = traffic.get_traffic_for_route(
                    [(52.4, 4.8), (52.42, 4.82)])
        self.assertEqual(len(report["segments"]), 1)

    def test_all_segments_bad_is_an_error(self):
        fake = _fake_urlopen_factory([
            ("flowSegmentData", {}),
            ("incidentDetails", INCIDENTS_OK),
        ])
        with patch.dict(os.environ, {"TOMTOM_API_KEY": "k"}):
            with patch("urllib.request.urlopen", fake):
                with self.assertRaises(TrafficError):
                    traffic.get_traffic_for_route([(52.4, 4.8)])


if __name__ == "__main__":
    unittest.main()
