"""Way2 — trip state and deterministic voice-command parsing.

The intent parser is regex/keyword based — no LLM. Fast, offline, predictable.
Intent vocabulary matches docs/CONTRACT.md exactly (the app dispatches
`_on_<intent>` on these names).

Trip is the source of truth for stop order and routing: it hands waypoint
labels to way2.geo (which geocodes place names on the fly) and caches
the route until the trip changes.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

# Intent names the app layer switches on. Do not rename without updating
# docs/CONTRACT.md and way2/app.py.
INTENTS = (
    "set_origin",
    "set_destination",
    "add_stop",
    "skip_next",
    "eta",
    "summary",
    "find_places",
    "weather",
    "faster_route",
    "traffic",
    "help",
    "quit",
    "unknown",
)

_PATTERNS: list[tuple[str, re.Pattern]] = [
    (
        "set_origin",
        re.compile(
            r"^\s*(?:starting from|start from|my location is|i'?m (?:at|in)|i am (?:at|in))"
            r"\s+(?P<origin>.+?)[.?!]*$",
            re.IGNORECASE,
        ),
    ),
    (
        "set_destination",
        re.compile(
            r"\b(?:take me to|navigate to|drive to|go to|directions to|head to)"
            r"\s+(?P<destination>.+?)[.?!]*$",
            re.IGNORECASE,
        ),
    ),
    (
        "add_stop",
        re.compile(
            r"\badd (?:a )?stop (?:at|in|near)\s+(?P<stop>.+?)[.?!]*$",
            re.IGNORECASE,
        ),
    ),
    (
        "skip_next",
        re.compile(r"\bskip(?: the)?(?: next)? stop\b", re.IGNORECASE),
    ),
    (
        "eta",
        re.compile(
            r"\b(what'?s my eta|\beta\b|when will i (?:arrive|get there)"
            r"|how long (?:until|till)|arrival time|how much longer)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "summary",
        re.compile(
            r"\b(trip summary|summariz(?:e|ing)(?: my| the)? trip)\b|^\s*summary\s*[.?!]*$",
            re.IGNORECASE,
        ),
    ),
    (
        "find_places",
        re.compile(
            r"\bfind (?P<category>scenic|nightlife|shows|food)"
            r"(?:\s+(?:spots?|places?))?(?:\s+near\s+(?P<near>.+?))?[.?!]*$",
            re.IGNORECASE,
        ),
    ),
    # Food / lunch aliases -> find_places with the "food" category.
    (
        "find_places",
        re.compile(
            r"\b(?:plan lunch(?: along the route)?|i'?m hungry|where can i eat"
            r"|find (?:lunch|restaurants?|food)|grab (?:a )?bite(?: to eat)?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "weather",
        re.compile(
            r"\bweather (?:along|on)(?: my| the)? route\b|\bwill it rain\b"
            r"|\bstorms? (?:ahead|on (?:my|the) route)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "faster_route",
        re.compile(
            r"\b(?:any |a )?faster route\b|\bquicker way\b|\breroute\b"
            r"|\bbetter route\b",
            re.IGNORECASE,
        ),
    ),
    (
        "traffic",
        re.compile(
            r"\btraffic (?:on|along)(?: my| the)? route\b"
            r"|\bhow'?s (?:the )?traffic\b|\bany traffic (?:ahead|on (?:my|the) route)?\b"
            r"|\btraffic (?:ahead|report|update)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "help",
        re.compile(r"^\s*help\s*[.?!]*$", re.IGNORECASE),
    ),
    (
        "quit",
        re.compile(r"^\s*(quit|exit|bye|goodbye|stop)\s*[.?!]*$", re.IGNORECASE),
    ),
]


def parse_command(text: str) -> dict:
    """Parse a spoken command into {"intent": ..., "params": {...}}.

    Always returns a dict; unrecognized input yields intent "unknown"
    with the raw text in params.
    """
    cleaned = (text or "").strip()
    for intent, pattern in _PATTERNS:
        match = pattern.search(cleaned)
        if match:
            params = {
                key: value.strip(" .?!")
                for key, value in match.groupdict().items()
                if value
            }
            if intent == "find_places":
                # The lunch-alias pattern has no named groups.
                params.setdefault("category", "food")
                params.setdefault("near", "")
            return {"intent": intent, "params": params}
    return {"intent": "unknown", "params": {"text": cleaned}}


def _duration_min(route) -> float:
    """Drive minutes from a route dict, accepting either unit style."""
    if isinstance(route, dict):
        if route.get("duration_min") is not None:
            return float(route["duration_min"])
        return float(route.get("duration_s", 0) or 0) / 60.0
    if getattr(route, "duration_min", None) is not None:
        return float(route.duration_min)
    return float(getattr(route, "duration_s", 0) or 0) / 60.0


def _distance_mi(route) -> float:
    if isinstance(route, dict):
        if route.get("distance_mi") is not None:
            return float(route["distance_mi"])
        return float(route.get("distance_m", 0) or 0) / 1609.344
    if getattr(route, "distance_mi", None) is not None:
        return float(route.distance_mi)
    return float(getattr(route, "distance_m", 0) or 0) / 1609.344


def _geometry(route) -> list[tuple[float, float]]:
    if isinstance(route, dict):
        geom = route.get("geometry", [])
    else:
        geom = getattr(route, "geometry", [])
    return [(float(lat), float(lon)) for lat, lon in geom]


class Trip:
    """A driving trip: origin label plus an ordered list of stop labels.

    The source of truth for stop order (see docs/CONTRACT.md). Waypoint
    labels go straight to way2.geo, which geocodes place names on the
    fly; the route is cached until the trip changes. Pass geo_mod= in
    tests to avoid real network calls.
    """

    def __init__(self, origin: str = "current location", geo_mod=None):
        self.origin_label = origin
        self.stops: list[str] = []
        self._geo_mod = geo_mod
        self._route = None

    def _geo(self):
        if self._geo_mod is not None:
            return self._geo_mod
        from way2 import geo  # partner-owned; imported lazily

        return geo

    def set_origin(self, label: str) -> None:
        """Set the starting point. Called by the app's set_origin handler."""
        label = (label or "").strip()
        if not label:
            raise ValueError("set_origin needs a place name.")
        self.origin_label = label
        self._route = None

    def add_stop(self, label: str) -> None:
        label = (label or "").strip()
        if not label:
            raise ValueError("add_stop needs a place name.")
        self.stops.append(label)
        self._route = None

    def skip_next(self) -> str:
        """Drop the most recently added stop; returns its label.

        The first stop is the trip's destination and is never skipped —
        with nothing but the destination left, there are no upcoming
        stops to skip.
        """
        if len(self.stops) <= 1:
            raise ValueError("There are no upcoming stops to skip.")
        skipped = self.stops.pop()
        self._route = None
        return skipped

    @property
    def waypoints(self) -> list[str]:
        return [self.origin_label, *self.stops]

    def current_route(self):
        """Route dict for origin -> stops, via way2.geo."""
        if self._route is None:
            if not self.stops:
                raise ValueError("No destination set yet — say 'navigate to …' first.")
            self._route = self._geo().route(self.waypoints)
        return self._route

    def midpoint(self) -> tuple[float, float] | None:
        """Lat/lon of the route's geometric midpoint, or None if unknown."""
        geom = _geometry(self.current_route())
        if not geom:
            return None
        return geom[len(geom) // 2]

    def eta(self) -> str:
        """Human-readable ETA, e.g. 'About 24 minutes — arriving around 1:15 PM.'"""
        mins = _duration_min(self.current_route())
        arrival = datetime.now() + timedelta(minutes=mins)
        clock = arrival.strftime("%-I:%M %p").lstrip("0")
        return f"About {mins:.0f} minutes — arriving around {clock}."

    def summary(self) -> str:
        """Human-readable trip summary."""
        if not self.stops:
            return "No trip planned yet — say 'navigate to …' to set a destination."
        route = self.current_route()
        legs = " → ".join(self.waypoints)
        return (
            f"{legs}: about {_duration_min(route):.0f} minutes, "
            f"{_distance_mi(route):.1f} miles."
        )
