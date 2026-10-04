#!/usr/bin/env python3
"""Way2 — hands-free smart GPS for people who drive for work.

Conversation loop: a command comes in as text (typed, or transcribed from
voice), trip.parse_command() figures out the intent deterministically, and
this loop carries it out — geocoding and routing on open data, weather
alerts from Open-Meteo, spoken responses when voice mode is on.

Partner-owned modules (top level; exact signatures in docs/CONTRACT.md):
    trip.parse_command(text) -> {"intent": str, "params": dict}
    trip.Trip: set_origin / add_stop / skip_next / eta / summary /
               current_route / midpoint / waypoints
    weather.alerts_along_route(route) -> [str]
    alerts.check_faster_route(trip) -> str | None

Run (from the repo root):
    python3 -m way2.app            # text mode (demo-friendly)
    python3 -m way2.app --voice    # voice in + voice out (needs whisper + mic)
    python3 -m way2.app --say      # text in, spoken responses too
"""

from __future__ import annotations

import argparse
import sys

from way2 import geo, traffic
from way2.geo import GeoError
from way2.traffic import TrafficError
from way2.voice import (
    VoiceError, listen, speak, transcribe_file, whisper_available,
)

BANNER = r"""
 __        __          ____
 \ \      / /_ _ _   _|___ \
  \ \ /\ / / _` | | | | __) |
   \ V  V / (_| | |_| |/ __/
    \_/\_/ \__,_|\__, |_____|
                 |___/
  Hands-free GPS for people who drive for work.
"""


# ---------------------------------------------------------------------------
# Startup: verify the partner modules are in place with the agreed signatures.
# ---------------------------------------------------------------------------

def _load_partners():
    try:
        from way2 import trip, weather, alerts
    except ImportError as e:
        sys.exit(f"Way2 can't start: partner module missing ({e}). "
                 "See docs/CONTRACT.md.")
    for name, obj, attrs in (("trip", trip, ["parse_command", "Trip"]),
                             ("weather", weather, ["alerts_along_route"]),
                             ("alerts", alerts, ["check_faster_route"])):
        for a in attrs:
            if not hasattr(obj, a):
                sys.exit(f"Way2 can't start: {name}.{a} is missing "
                         f"(see docs/CONTRACT.md).")
    for m in ("set_origin", "add_stop", "skip_next", "eta", "summary",
              "current_route", "midpoint", "waypoints"):
        if not hasattr(trip.Trip, m):
            sys.exit(f"Way2 can't start: trip.Trip.{m} is missing "
                     f"(see docs/CONTRACT.md).")
    return trip, weather, alerts


class Driver:
    """Owns the conversation. trip.Trip owns the stops and routing."""

    def __init__(self, trip_mod, weather_mod, alerts_mod, voice_mode=False, say=False):
        self.trip_mod = trip_mod
        self.weather_mod = weather_mod
        self.alerts_mod = alerts_mod
        self.voice_mode = voice_mode
        self.say = say or voice_mode
        self.trip = trip_mod.Trip()
        self.origin_set = False

    # -- input / output ----------------------------------------------------
    def get_command(self) -> str | None:
        if self.voice_mode:
            print("(listening — speak your command)")
            try:
                return listen()
            except VoiceError as e:
                print(f"[voice] {e}")
                return ""
        try:
            return input("you> ")
        except (EOFError, KeyboardInterrupt):
            return None

    def reply(self, text: str):
        print(f"way2> {text}")
        if self.say:
            try:
                # Speak the gist: first sentence, so it stays hands-free short.
                speak(text.split(". ")[0].rstrip(".") + ".")
            except VoiceError as e:
                print(f"[voice] {e}")

    # -- routing helpers -----------------------------------------------------
    def _route_or_error(self):
        """(route, error_message) — route is the dict from geo.route()."""
        if not self.origin_set:
            return None, ("Where are you starting from? "
                          "Say 'starting from' and your town.")
        if not self.trip.stops:
            return None, ("There's nowhere to go yet. "
                          "Say 'navigate to' and a destination.")
        try:
            return self.trip.current_route(), None
        except (GeoError, ValueError, RuntimeError) as e:
            return None, str(e)

    @staticmethod
    def _describe_route(r: dict) -> str:
        mins = r.get("duration_min")
        if mins is None:
            mins = r.get("duration_s", 0) / 60
        miles = r.get("distance_mi")
        if miles is None:
            miles = r.get("distance_m", 0) / 1609.344
        return f"{miles:.1f} miles, about {mins:.0f} minutes of driving"

    # -- dispatch --------------------------------------------------------------
    def handle(self, text: str) -> str | None:
        """Returns reply text, or None to quit."""
        parsed = self.trip_mod.parse_command(text or "")
        intent = parsed.get("intent", "unknown")
        params = parsed.get("params", {}) or {}
        handler = getattr(self, f"_on_{intent}", self._on_unknown)
        return handler(params, text)

    # -- intent handlers ---------------------------------------------------------
    def _on_set_origin(self, p, _):
        try:
            g = geo.geocode(p.get("origin", ""))
        except GeoError as e:
            return str(e)
        self.trip.set_origin(g["label"])
        self.origin_set = True
        return f"Got it — starting from {g['label']}."

    def _on_set_destination(self, p, _):
        dest = (p.get("destination") or "").strip()
        if not dest:
            return "Navigate where? Name a destination."
        try:
            g = geo.geocode(dest)
        except GeoError as e:
            return str(e)
        try:
            self.trip.add_stop(g["label"])
        except ValueError as e:
            return str(e)
        r, err = self._route_or_error()
        if err:
            return f"Destination set: {g['label']}. {err}"
        return f"Destination set: {g['label']}. {self._describe_route(r)}."

    def _on_add_stop(self, p, _):
        place = (p.get("stop") or "").strip()
        if not place:
            return "Add a stop where? Name the place."
        try:
            g = geo.geocode(place)
        except GeoError as e:
            return str(e)
        try:
            self.trip.add_stop(g["label"])
        except ValueError as e:
            return str(e)
        r, err = self._route_or_error()
        if err:
            return f"Added a stop at {g['label']}. {err}"
        return f"Added a stop at {g['label']}. {self._describe_route(r)}."

    def _on_skip_next(self, p, _):
        try:
            skipped = self.trip.skip_next()
        except ValueError:
            return "There are no upcoming stops to skip."
        except Exception as e:
            return f"Couldn't skip: {e}"
        r, err = self._route_or_error()
        tail = "" if err else f" New route: {self._describe_route(r)}."
        return f"Skipped {skipped}.{tail}"

    def _on_eta(self, p, _):
        r, err = self._route_or_error()
        if err:
            return err
        try:
            return str(self.trip.eta())
        except Exception as e:
            return f"Couldn't get the ETA: {e}"

    def _on_summary(self, p, _):
        if not self.trip.stops:
            return str(self.trip.summary())
        r, err = self._route_or_error()
        if err:
            return err
        try:
            out = str(self.trip.summary())
        except Exception as e:
            return f"Couldn't summarize the trip: {e}"
        try:
            wx = self.weather_mod.alerts_along_route(r)
        except Exception:
            wx = []
        if wx:
            out += "\nWeather on your route:\n- " + "\n- ".join(wx)
        try:
            faster = self.alerts_mod.check_faster_route(self.trip)
        except Exception:
            faster = None
        if faster:
            out += f"\n{faster}"
        return out

    def _on_find_places(self, p, _):
        category = (p.get("category") or "").lower()
        near = (p.get("near") or "").strip()
        try:
            if near:
                g = geo.geocode(near)
                lat, lon, where = g["lat"], g["lon"], g["label"]
            elif self.origin_set:
                g = geo.geocode(self.trip.origin_label)
                lat, lon, where = g["lat"], g["lon"], g["label"]
            else:
                return "Near where? Say 'starting from …' first, or name a place."
            places = geo.find_places(lat, lon, category)
        except GeoError as e:
            return str(e)
        if not places:
            return f"Didn't find any {category} spots near {where}."
        lines = [f"{pl['name']}" for pl in places[:3]]
        return f"Near {where} I see: " + "; ".join(lines) + "."

    def _on_weather(self, p, _):
        r, err = self._route_or_error()
        if err:
            return err
        try:
            wx = self.weather_mod.alerts_along_route(r)
        except Exception as e:
            return f"Weather check failed: {e}"
        if not wx:
            return "No weather alerts on your route. Clear driving."
        return "Weather on your route:\n- " + "\n- ".join(wx)

    def _live_traffic_note(self, route: dict) -> str | None:
        """One-line live-traffic summary, or None when unavailable."""
        if not traffic.api_key():
            return None
        try:
            pts = [(lat, lon) for lat, lon in (route.get("geometry") or [])]
            rep = traffic.get_traffic_for_route(pts)
        except Exception:
            return None
        delay_min = rep.get("summary", {}).get("total_delay_sec", 0) / 60
        if delay_min < 1 and not rep.get("incidents"):
            return "Live traffic: flowing freely on your route."
        parts = [f"Live traffic: about {delay_min:.0f} min of delay on your route."]
        for inc in rep.get("incidents", [])[:2]:
            parts.append(f"{inc.get('category')}: {inc.get('description')}")
        return " ".join(parts)

    def _on_traffic(self, p, _):
        r, err = self._route_or_error()
        if err:
            return err
        try:
            pts = [(lat, lon) for lat, lon in (r.get("geometry") or [])]
            rep = traffic.get_traffic_for_route(pts)
        except TrafficError as e:
            return str(e)
        except Exception as e:
            return f"Traffic check failed: {e}"
        lines = [rep.get("summary", {}).get("headline", "Traffic checked.")]
        for inc in rep.get("incidents", [])[:3]:
            lines.append(f"- {inc.get('category')}: {inc.get('description')}")
        return "\n".join(lines)

    def _on_faster_route(self, p, _):
        r, err = self._route_or_error()
        if err:
            return err
        try:
            faster = self.alerts_mod.check_faster_route(self.trip)
        except Exception as e:
            return f"Couldn't check for a faster route: {e}"
        base = faster or "You're already on the fastest route I can see."
        live = self._live_traffic_note(r)
        if live:
            return f"{base}\n{live}"
        if traffic.api_key():
            return base  # key set, traffic checked, nothing notable
        return (base + " (Road network only — set TOMTOM_API_KEY "
                "for live traffic.)")

    def _on_help(self, p, _):
        return ("Try: 'starting from Cherry Hill', 'navigate to Philadelphia', "
                "'add a stop in Camden', 'skip the next stop', "
                "\"what's my ETA\", 'find restaurants', 'find scenic spots', "
                "'weather along the route', 'traffic on my route', "
                "'any faster route', 'trip summary', or 'quit'.")

    def _on_quit(self, p, _):
        return None

    def _on_unknown(self, p, text):
        return ("I didn't catch that as a driving command. " + self._on_help({}, ""))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="way2",
                                 description="Way2 — hands-free GPS.")
    ap.add_argument("--voice", action="store_true",
                    help="voice in (mic) + voice out (needs whisper + mic)")
    ap.add_argument("--say", action="store_true",
                    help="speak responses aloud in text mode")
    ap.add_argument("--transcribe", metavar="AUDIO",
                    help="transcribe an audio file instead of the mic, one shot")
    args = ap.parse_args(argv)

    trip_mod, weather_mod, alerts_mod = _load_partners()
    print(BANNER)
    if args.voice and not whisper_available():
        print("[voice] Whisper isn't installed — voice input will fall back "
              "to typed commands. (pip install openai-whisper)")

    if args.transcribe:
        try:
            print(transcribe_file(args.transcribe))
        except VoiceError as e:
            sys.exit(f"Couldn't transcribe: {e}")
        return

    driver = Driver(trip_mod, weather_mod, alerts_mod,
                    voice_mode=args.voice, say=args.say)
    print("Tell me where you're driving. Type 'help' for examples, 'quit' to stop.\n")
    while True:
        text = driver.get_command()
        if text is None:  # EOF / Ctrl-C
            print("\nway2> Drive safe.")
            break
        if not text.strip():
            continue
        reply = driver.handle(text)
        if reply is None:
            print("way2> Drive safe.")
            break
        driver.reply(reply)


if __name__ == "__main__":
    main()
