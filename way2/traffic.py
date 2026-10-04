"""Way2 — real-time traffic via TomTom.

Flow speeds and incidents along a route, from the TomTom Traffic API
(flowSegmentData v4 + incidentDetails v5). Needs a free TomTom API key in
the TOMTOM_API_KEY environment variable — the key is never logged, never
hardcoded, and never leaves the request URL.

get_traffic_for_route(points) takes a list of (lat, lon) pairs and returns
a plain dict:

    {
        "segments": [
            {"lat": ..., "lon": ...,
             "current_speed_kmh": 42.0, "free_flow_speed_kmh": 80.0,
             "delay_sec": 35, "congestion_pct": 47.5,
             "confidence": 0.8, "road_closure": False},
            ...
        ],
        "incidents": [
            {"id": "abc123", "category": "Jam",
             "description": "...", "delay_sec": 300,
             "length_m": 1200, "magnitude": "Moderate"},
            ...
        ],
        "summary": {"segments_checked": 5, "total_delay_sec": 335,
                    "worst_congestion_pct": 47.5,
                    "headline": "Heavy traffic on 2 of 5 segments"},
    }

Every function raises TrafficError with a plain-language message when the
key is missing or the API can't be reached, so the text loop keeps working.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

FLOW_URL = "https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/10/json"
INCIDENTS_URL = "https://api.tomtom.com/traffic/services/5/incidentDetails"
REQUEST_TIMEOUT = 15
MAX_FLOW_POINTS = 8  # keep request counts sane on the free tier
HEAVY_CONGESTION_PCT = 30.0  # segment counts as "heavy" at this slowdown

# TomTom iconCategory -> plain words (Traffic Incidents API).
_INCIDENT_CATEGORIES = {
    1: "Accident", 2: "Fog", 3: "Dangerous Conditions", 4: "Rain",
    5: "Ice", 6: "Jam", 7: "Lane Closed", 8: "Road Closed",
    9: "Road Works", 10: "Wind", 11: "Flooding",
    14: "Broken-Down Vehicle",
}
# TomTom magnitudeOfDelay -> plain words.
_DELAY_MAGNITUDE = {
    0: "Unknown", 1: "Minor", 2: "Moderate", 3: "Major", 4: "Closure",
}


class TrafficError(Exception):
    """The traffic service isn't available or couldn't answer."""


def api_key() -> str | None:
    """The TomTom key, or None when it isn't configured."""
    key = os.environ.get("TOMTOM_API_KEY", "").strip()
    return key or None


def _require_key() -> str:
    key = api_key()
    if not key:
        raise TrafficError(
            "Live traffic needs a TomTom API key. Set the TOMTOM_API_KEY "
            "environment variable (free at developer.tomtom.com) and try again.")
    return key


def _get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "way2/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as res:
            return json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 403:
            raise TrafficError(
                "TomTom rejected the request (403) — the API key may be "
                "invalid or out of quota.") from e
        raise TrafficError(f"TomTom answered with HTTP {e.code}.") from e
    except urllib.error.URLError as e:
        raise TrafficError(
            "Couldn't reach TomTom — check your connection and try again.") from e
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise TrafficError("TomTom sent back something I couldn't read.") from e


def _sample_points(points: list, n: int = MAX_FLOW_POINTS) -> list:
    pts = [(float(lat), float(lon)) for lat, lon in points]
    if len(pts) <= n:
        return pts
    step = (len(pts) - 1) / (n - 1)
    return [pts[round(i * step)] for i in range(n)]


def flow_at_point(lat: float, lon: float, key: str | None = None) -> dict:
    """Flow data for the road segment nearest one point.

    Returns current_speed_kmh, free_flow_speed_kmh, delay_sec,
    congestion_pct, confidence, road_closure. Raises TrafficError when the
    point isn't on a known segment or the API fails.
    """
    key = key or _require_key()
    query = urllib.parse.urlencode({
        "point": f"{lat},{lon}",
        "unit": "KMPH",
        "key": key,
    })
    data = _get_json(f"{FLOW_URL}?{query}")
    seg = data.get("flowSegmentData")
    if not seg:
        raise TrafficError(
            "TomTom has no flow data for that spot — it may be off the road network.")
    current = float(seg.get("currentSpeed", 0))
    free = float(seg.get("freeFlowSpeed", 0))
    delay = max(0, int(seg.get("currentTravelTime", 0)) - int(seg.get("freeFlowTravelTime", 0)))
    congestion = round(100.0 * (1 - current / free), 1) if free > 0 else 0.0
    return {
        "lat": lat, "lon": lon,
        "current_speed_kmh": current,
        "free_flow_speed_kmh": free,
        "delay_sec": delay,
        "congestion_pct": congestion,
        "confidence": float(seg.get("confidence", 0)),
        "road_closure": bool(seg.get("roadClosure", False)),
    }


def incidents_along_route(points: list, key: str | None = None) -> list:
    """Incidents inside the bounding box of the route.

    Returns a list of {id, category, description, delay_sec, length_m,
    magnitude}. Empty list = nothing reported.
    """
    key = key or _require_key()
    pts = [(float(lat), float(lon)) for lat, lon in points]
    if not pts:
        return []
    lats = [p[0] for p in pts]
    lons = [p[1] for p in pts]
    bbox = f"{min(lons)},{min(lats)},{max(lons)},{max(lats)}"
    fields = ("{incidents{type,geometry{type,coordinates},"
              "properties{id,iconCategory,magnitudeOfDelay,delay,length,"
              "events{description}}}}")
    query = urllib.parse.urlencode({
        "bbox": bbox,
        "fields": fields,
        "language": "en-US",
        "timeValidityFilter": "present",
        "key": key,
    })
    data = _get_json(f"{INCIDENTS_URL}?{query}")
    out = []
    for inc in data.get("incidents", []):
        props = inc.get("properties", {}) or {}
        events = props.get("events") or []
        description = ""
        if events and isinstance(events[0], dict):
            description = events[0].get("description", "") or ""
        out.append({
            "id": str(props.get("id", "")),
            "category": _INCIDENT_CATEGORIES.get(props.get("iconCategory"), "Incident"),
            "description": description,
            "delay_sec": int(props.get("delay") or 0),
            "length_m": int(props.get("length") or 0),
            "magnitude": _DELAY_MAGNITUDE.get(props.get("magnitudeOfDelay"), "Unknown"),
        })
    return out


def get_traffic_for_route(points: list, key: str | None = None) -> dict:
    """Traffic for a route: per-segment flow speeds plus incidents.

    points: list of (lat, lon) pairs. key: TomTom API key, or None to read
    TOMTOM_API_KEY from the environment. Raises TrafficError with a
    plain-language message when the key is missing or TomTom can't answer.
    """
    key = key or _require_key()
    pts = [(float(lat), float(lon)) for lat, lon in points]
    if not pts:
        raise TrafficError("There's no route to check traffic on.")
    sampled = _sample_points(pts)
    segments = []
    for lat, lon in sampled:
        try:
            segments.append(flow_at_point(lat, lon, key=key))
        except TrafficError:
            # One bad segment shouldn't sink the whole route.
            continue
    if not segments:
        raise TrafficError("TomTom had no flow data for any point on that route.")
    incidents = incidents_along_route(pts, key=key)
    total_delay = sum(s["delay_sec"] for s in segments)
    worst = max(s["congestion_pct"] for s in segments)
    heavy = sum(1 for s in segments if s["congestion_pct"] >= HEAVY_CONGESTION_PCT)
    if heavy:
        headline = (f"Heavy traffic on {heavy} of {len(segments)} segments, "
                    f"about {total_delay // 60} min of delay")
    elif total_delay > 0:
        headline = f"Light delays, about {total_delay // 60} min total"
    else:
        headline = "Traffic is flowing freely"
    return {
        "segments": segments,
        "incidents": incidents,
        "summary": {
            "segments_checked": len(segments),
            "total_delay_sec": total_delay,
            "worst_congestion_pct": worst,
            "headline": headline,
        },
    }