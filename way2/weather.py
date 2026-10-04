"""Way2 — weather alerts along a route, via Open-Meteo.

Free, no API key. Samples a few points along the route geometry, fetches
current conditions for each, and returns spoken-style alert strings for
rain, storms, snow, fog, high wind, and extreme temperatures.
Empty list = nothing to warn about.

Needs the route to carry a `geometry` list of (lat, lon) pairs
(see docs/CONTRACT.md). If the route has no shape data, raises WeatherError
with a plain-language message instead of pretending the sky is clear.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
REQUEST_TIMEOUT = 15

# WMO weather codes: https://open-meteo.com/en/docs
_THUNDERSTORM = {95, 96, 99}
_HEAVY_RAIN = {65, 66, 67, 82}
_LIGHT_RAIN = {51, 53, 55, 56, 57, 61, 63, 80, 81}
_SNOW = {71, 73, 75, 77, 85, 86}
_FOG = {45, 48}

HIGH_WIND_KMH = 40.0
EXTREME_HEAT_C = 38.0
EXTREME_COLD_C = -12.0


class WeatherError(Exception):
    pass


def _geometry_points(route) -> list[tuple[float, float]]:
    if isinstance(route, dict):
        geom = route.get("geometry", [])
    else:
        geom = getattr(route, "geometry", [])
    return [(float(lat), float(lon)) for lat, lon in geom]


def sample_points(route, n: int = 5) -> list[tuple[float, float]]:
    """Evenly spaced lat/lon points along the route geometry."""
    geom = _geometry_points(route)
    if not geom:
        return []
    if len(geom) <= n:
        return geom
    step = (len(geom) - 1) / (n - 1)
    return [geom[round(i * step)] for i in range(n)]


def _point_label(index: int, total: int) -> str:
    if total <= 1:
        return "on your route"
    if index == 0:
        return "near your starting point"
    if index == total - 1:
        return "near your destination"
    return "along the way"


def fetch_current(lat: float, lon: float) -> dict:
    """Current conditions from Open-Meteo. Raises WeatherError on failure."""
    query = urllib.parse.urlencode(
        {
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,precipitation,weather_code,wind_speed_10m",
            "timezone": "auto",
        }
    )
    request = urllib.request.Request(
        f"{OPEN_METEO_URL}?{query}",
        headers={"User-Agent": "GodsEyeView/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise WeatherError(f"Couldn't reach the weather service: {exc}") from exc
    current = payload.get("current")
    if not current:
        raise WeatherError("Weather service returned no current conditions.")
    return current


def alerts_for_point(label: str, current: dict) -> list[str]:
    """Spoken-style alerts for one point's current conditions."""
    alerts: list[str] = []
    code = int(current.get("weather_code", 0) or 0)
    wind = float(current.get("wind_speed_10m", 0) or 0)
    temp = current.get("temperature_2m")

    if code in _THUNDERSTORM:
        alerts.append(f"Thunderstorms {label} — expect slowdowns and slick roads.")
    elif code in _HEAVY_RAIN:
        alerts.append(f"Heavy rain {label} — give yourself extra space.")
    elif code in _SNOW:
        alerts.append(f"Snow {label} — take it easy out there.")
    elif code in _FOG:
        alerts.append(f"Fog {label} — visibility is low, lights on.")
    elif code in _LIGHT_RAIN:
        alerts.append(f"Light rain {label} — roads may be slick.")

    if wind >= HIGH_WIND_KMH:
        alerts.append(f"High winds {label} — gusts around {wind:.0f} km/h.")

    if temp is not None:
        temp = float(temp)
        if temp >= EXTREME_HEAT_C:
            alerts.append(f"Extreme heat {label} — {temp:.0f} degrees. Keep water handy.")
        elif temp <= EXTREME_COLD_C:
            alerts.append(f"Extreme cold {label} — {temp:.0f} degrees. Watch for ice.")

    return alerts


def alerts_along_route(route) -> list[str]:
    """Spoken-style weather alerts for points along the route.

    `route` is the dict from geo.route(), which must include a `geometry`
    list of (lat, lon) pairs. Weather-service failures degrade to [] (the
    drive continues); a route with no shape data raises WeatherError,
    because "no alerts" would be a lie.
    """
    points = sample_points(route)
    if not points:
        raise WeatherError(
            "I couldn't get the shape of your route, so I can't check "
            "the weather along it."
        )
    alerts: list[str] = []
    for i, (lat, lon) in enumerate(points):
        label = _point_label(i, len(points))
        try:
            current = fetch_current(lat, lon)
        except WeatherError:
            continue
        alerts.extend(alerts_for_point(label, current))
    # De-dupe identical alerts (e.g. same storm seen at two sample points).
    seen: set[str] = set()
    unique: list[str] = []
    for alert in alerts:
        if alert not in seen:
            seen.add(alert)
            unique.append(alert)
    return unique
