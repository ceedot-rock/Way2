"""Way2 — faster-route checks against OSRM alternative routes.

Honest framing, always: OSRM alternatives describe the road network, not
live traffic — there is no good open source for real-time traffic. This
module tells the driver when a different route option is meaningfully
quicker on paper, and the write-up says plainly that live traffic is next.

Needs the route to carry an `alternatives` list of route-shaped dicts
(see docs/CONTRACT.md). Without alternative data there is nothing to
compare, which raises a plain-language error instead of a false "you're
already fastest".
"""

from __future__ import annotations


def _duration_min(route) -> float:
    if isinstance(route, dict):
        if "duration_s" in route:
            return float(route.get("duration_s", 0) or 0) / 60.0
        return float(route.get("duration_min", 0) or 0)
    if hasattr(route, "duration_s"):
        return float(route.duration_s or 0) / 60.0
    return float(getattr(route, "duration_min", 0) or 0)


def _alternatives(route) -> list | None:
    """None when the route carries no alternative data at all."""
    if isinstance(route, dict):
        return route.get("alternatives")
    return getattr(route, "alternatives", None)


def check_faster_route(trip) -> str | None:
    """Spoken alert if a meaningfully faster route option exists.

    "Meaningfully" = saves more than 5 minutes, or more than 10% of the
    current drive time. Returns None when the current route is already the
    fastest of the options. Raises RuntimeError with a plain message when
    there is no alternative-route data to compare against.
    """
    route = trip.current_route()
    current_min = _duration_min(route)
    if current_min <= 0:
        return None

    alternatives = _alternatives(route)
    if alternatives is None:
        raise RuntimeError(
            "I couldn't pull up alternative routes right now, "
            "so I can't say whether a faster way exists."
        )
    if not alternatives:
        return None

    best = min(alternatives, key=_duration_min)
    best_min = _duration_min(best)
    saved = current_min - best_min

    if saved > 5 or saved / current_min > 0.10:
        return (
            f"Heads up — there's a faster way. It saves about {saved:.0f} minutes "
            f"off your {current_min:.0f}-minute drive. Want me to switch you over?"
        )
    return None
