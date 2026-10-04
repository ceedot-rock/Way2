"""Way2 — open-data geography: geocoding, routing, POI search.

Backends (all free, no API keys):
  - Nominatim (OpenStreetMap) for geocoding and place search
  - OSRM public demo server for driving routes

Nominatim's usage policy requires <= 1 request/second and an identifying
User-Agent; this module throttles itself to comply. Be nice to the commons.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.parse
import urllib.request

USER_AGENT = "GodsEyeView/1.0 (Hacktoberfest Weekend Challenge entry)"

NOMINATIM_BASE = "https://nominatim.openstreetmap.org"
OSRM_BASE = "https://router.project-osrm.org"


class GeoError(Exception):
    """Anything that goes wrong talking to the geo backends."""


# ---------------------------------------------------------------------------
# Polite HTTP: 1 req/s throttle for Nominatim, shared across threads.
# ---------------------------------------------------------------------------

_throttle_lock = threading.Lock()
_last_request_at = 0.0


def _throttled_get(url: str, timeout: int = 15) -> bytes:
    global _last_request_at
    with _throttle_lock:
        wait = 1.0 - (time.monotonic() - _last_request_at)
        if wait > 0:
            time.sleep(wait)
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as res:
                data = res.read()
        except Exception as e:  # network errors, HTTP errors, timeouts
            raise GeoError(f"Couldn't reach the map service: {e}") from e
        _last_request_at = time.monotonic()
        return data


# ---------------------------------------------------------------------------
# Geocoding
# ---------------------------------------------------------------------------

def geocode(address: str) -> dict:
    """geocode(address) -> {"lat": float, "lon": float, "label": str}.

    Raises GeoError when the address can't be found or the service fails.
    """
    address = (address or "").strip()
    if not address:
        raise GeoError("I need an address or place name to look up.")
    params = urllib.parse.urlencode({
        "q": address, "format": "json", "limit": 1, "addressdetails": 1,
    })
    try:
        results = json.loads(_throttled_get(f"{NOMINATIM_BASE}/search?{params}"))
    except json.JSONDecodeError as e:
        raise GeoError(f"Map service sent back garbage: {e}") from e
    if not results:
        raise GeoError(f"Couldn't find '{address}'. Try a nearby landmark or ZIP code.")
    top = results[0]
    try:
        return {
            "lat": float(top["lat"]),
            "lon": float(top["lon"]),
            "label": top.get("display_name", address).split(",")[0],
        }
    except (KeyError, ValueError) as e:
        raise GeoError(f"Map service sent back an odd result: {e}") from e


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

_MANEUVERS = {
    "turn": "Turn",
    "new name": "Continue on",
    "depart": "Start on",
    "arrive": "Arrive at",
    "merge": "Merge onto",
    "on ramp": "Take the ramp onto",
    "off ramp": "Take the exit onto",
    "fork": "Keep",
    "end of road": "At the end of the road, turn onto",
    "roundabout": "At the roundabout, take",
    "rotary": "At the rotary, take",
    "roundabout turn": "At the roundabout, turn",
    "notification": "Continue on",
    "exit roundabout": "Exit the roundabout onto",
    "exit rotary": "Exit the rotary onto",
}


def _instruction(step: dict) -> str:
    man = step.get("maneuver", {})
    mtype = man.get("type", "")
    modifier = (man.get("modifier") or "").replace("slight ", "")
    name = step.get("name", "").strip()
    base = _MANEUVERS.get(mtype, "Continue")
    parts = [base]
    if modifier and mtype not in ("arrive", "depart", "new name"):
        parts.append(modifier)
    if name and mtype != "arrive":
        parts.append("onto" if parts[-1] in ("Turn", "Keep") else "")
        parts.append(name)
    text = " ".join(p for p in parts if p).strip()
    if mtype == "arrive":
        text = "Arrive at your destination"
    return text


def _resolve_points(points: list) -> list:
    """Turn mixed waypoints into [(lat, lon), ...].

    Each waypoint is either a (lat, lon) pair or a place-name string
    (geocoded via Nominatim). Raises GeoError on anything unresolvable.
    """
    resolved = []
    for p in points:
        if isinstance(p, str):
            g = geocode(p)
            resolved.append((g["lat"], g["lon"]))
        else:
            try:
                lat, lon = p
                resolved.append((float(lat), float(lon)))
            except (TypeError, ValueError) as e:
                raise GeoError(
                    f"Couldn't understand the waypoint {p!r}: "
                    "use a place name or a (lat, lon) pair.") from e
    return resolved


def route(points: list) -> dict:
    """route(points) -> {"distance_m", "duration_s", "duration_min",
    "distance_mi", "geometry", "alternatives", "steps": [...]}.

    points: at least 2 waypoints; each is a (lat, lon) pair or a
    place-name string (geocoded on the fly). Steps are
    {"instruction", "distance_m", "duration_s"} in driving order.
    geometry is [(lat, lon), ...] along the route (for weather sampling).
    alternatives are [{"duration_min", "distance_mi"}] for the other OSRM
    route options — road-network alternatives, NOT live traffic.
    Raises GeoError when no route exists or a service fails.
    """
    if len(points) < 2:
        raise GeoError("A route needs at least a start and a destination.")
    coords = ";".join(f"{lon},{lat}" for lat, lon in _resolve_points(points))
    params = urllib.parse.urlencode({
        "overview": "full", "geometries": "geojson",
        "steps": "true", "alternatives": "2",
    })
    url = f"{OSRM_BASE}/route/v1/driving/{coords}?{params}"
    try:
        payload = json.loads(_throttled_get(url, timeout=20))
    except json.JSONDecodeError as e:
        raise GeoError(f"Routing service sent back garbage: {e}") from e
    if payload.get("code") != "Ok" or not payload.get("routes"):
        raise GeoError("Couldn't find a driving route between those points.")
    routes = payload["routes"]
    r = routes[0]
    steps = []
    for leg in r.get("legs", []):
        for s in leg.get("steps", []):
            steps.append({
                "instruction": _instruction(s),
                "distance_m": round(s.get("distance", 0)),
                "duration_s": round(s.get("duration", 0)),
            })
    geom = [ (lat, lon) for lon, lat in
             (r.get("geometry", {}) or {}).get("coordinates", []) ]
    distance_m = round(r.get("distance", 0))
    duration_s = round(r.get("duration", 0))
    out = {
        "distance_m": distance_m,
        "duration_s": duration_s,
        "distance_mi": round(distance_m / 1609.344, 1),
        "duration_min": round(duration_s / 60, 1),
        "geometry": geom,
        "steps": steps,
        "alternatives": [
            {"duration_min": round(a.get("duration", 0) / 60, 1),
             "distance_mi": round(a.get("distance", 0) / 1609.344, 1)}
            for a in routes[1:]
        ],
    }
    return out


def format_distance(meters: float) -> str:
    miles = meters / 1609.344
    return f"{miles:.1f} miles"


def format_duration(seconds: float) -> str:
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m = rem // 60
    if h:
        return f"{h} hr {m} min"
    return f"{m} min"


# ---------------------------------------------------------------------------
# POI search
# ---------------------------------------------------------------------------

# category -> Nominatim search term. Kept small on purpose: these are the
# "life on the road" categories the drivers asked for.
PLACE_CATEGORIES = {
    "scenic": "viewpoint",
    "nightlife": "bar",
    "shows": "theatre",
    "food": "restaurant",
}


def find_places(lat: float, lon: float, category: str) -> list:
    """find_places(lat, lon, category) -> [{name, lat, lon, address}, ...].

    category is one of "scenic", "nightlife", "shows", "food".
    Raises GeoError on an unknown category or service failure.
    """
    term = PLACE_CATEGORIES.get((category or "").lower())
    if term is None:
        raise GeoError(
            f"I don't know the category '{category}'. "
            f"Try: {', '.join(sorted(PLACE_CATEGORIES))}.")
    # ~10 km box around the point — wide enough for suburbs.
    d = 0.09
    params = urllib.parse.urlencode({
        "q": term, "format": "json", "limit": 10,
        "viewbox": f"{lon-d},{lat+d},{lon+d},{lat-d}",
        "bounded": 1,
    })
    try:
        results = json.loads(_throttled_get(f"{NOMINATIM_BASE}/search?{params}"))
    except json.JSONDecodeError as e:
        raise GeoError(f"Map service sent back garbage: {e}") from e
    places = []
    seen_names = set()
    for r in results:
        try:
            name = r.get("display_name", term).split(",")[0]
            if name.lower() in seen_names:
                continue
            seen_names.add(name.lower())
            places.append({
                "name": name,
                "lat": float(r["lat"]),
                "lon": float(r["lon"]),
                "address": r.get("display_name", ""),
            })
        except (KeyError, ValueError):
            continue
    return places
