# Way2 — module contract (reconciled 2026-10-04, final)

Two builders, one repo. Layout: everything lives in the `way2` package.
This file is the law: don't change a signature without telling the other
builder. (Note: a root-level CONTRACT.md also exists from the partner with
older intent names — this file describes the interface as actually built.)

## Owned by ROADIE CORE (this side)

`way2/geo.py`
- `geocode(address) -> {"lat": float, "lon": float, "label": str}` — Nominatim,
  1 req/s self-throttle, `GeoError` on failure.
- `route(points) -> dict` — `points`: ≥2 waypoints, each a `(lat, lon)` pair
  or a place-name string (geocoded on the fly). OSRM `driving` profile.
  Returns `{"distance_m", "duration_s", "distance_mi", "duration_min",
  "geometry": [(lat, lon), ...], "steps": [{"instruction", "distance_m",
  "duration_s"}], "alternatives": [{"duration_min", "distance_mi"}]}`.
  Alternatives are road-network options — NOT live traffic. `GeoError` on
  failure.
- `find_places(lat, lon, category) -> [{"name","lat","lon","address"}]` —
  category in `{"scenic", "nightlife", "shows", "food"}` (mapped to Nominatim
  search terms `viewpoint`/`bar`/`theatre`/`restaurant`); `GeoError` otherwise.
- `GeoError(Exception)`, `format_distance(m)`, `format_duration(s)`.

`way2/voice.py`
- `transcribe_file(path) -> str` — local Whisper CLI (`--model tiny`,
  English); `VoiceError` when Whisper is missing or nothing was heard.
- `listen(max_seconds=10) -> str` — mic via arecord when available, else
  `VoiceError` with a plain-language fallback message.
- `speak(text) -> str` — TTS to a temp mp3, played via ffplay when present;
  returns the file path; `VoiceError` on failure.
- `VoiceError(Exception)`, `whisper_available() -> bool`.

`way2/app.py`
- Conversation loop; `Driver` holds a `trip.Trip` (source of truth for
  stops) plus an `origin_set` flag. Handles every intent the partner parser
  emits: `set_origin`, `set_destination`, `add_stop`, `skip_next`, `eta`,
  `summary`, `find_places`, `weather`, `faster_route`, `traffic`, `help`,
  `quit`, `unknown`. Text mode is the demo path; `--voice` / `--say` /
  `--transcribe FILE` flags for voice. `traffic` reads live TomTom data via
  `way2/traffic.py` (needs TOMTOM_API_KEY); the app says so plainly when
  the key is missing.

## Owned by PARTNER (intelligence)

`way2/trip.py`
- `parse_command(text) -> {"intent": str, "params": dict}` — DETERMINISTIC
  (regex/keyword), no LLM. Intents: `set_origin {origin}` ·
  `set_destination {destination}` · `add_stop {stop}` · `skip_next` ·
  `eta` · `summary` · `find_places {category, near}` (category in
  `scenic|nightlife|shows|food`; lunch aliases map to `food`) · `weather` ·
  `faster_route` · `traffic` · `help` · `quit` · `unknown {text}`.
- `Trip(origin="current location", geo_mod=None)`:
  `set_origin(label)`, `add_stop(label)` (ValueError on blank),
  `skip_next() -> str` (ValueError when ≤1 stop; the first stop is the
  destination and is never skipped), `waypoints`, `current_route()`
  (ValueError when no stops; resolves labels via `way2.geo`, cached),
  `midpoint()`, `eta() -> str`, `summary() -> str`.

`way2/weather.py`
- `alerts_along_route(route) -> [str]` — `route` is the dict from
  `geo.route()` (reads `geometry`). Open-Meteo, free, no key. Never raises
  for bad weather responses (returns []).

`way2/alerts.py`
- `check_faster_route(trip) -> str | None` — reads `trip.current_route()`
  and its `alternatives`; suggestion or `None`; raises `RuntimeError` with a
  plain message when no alternative data exists. Honest framing: road
  network, not live traffic.

## Shared honesty rules
- No traffic key, no fake traffic: the app says TOMTOM_API_KEY is missing
  and sticks to the road network. We do NOT fake it.
- Intent parsing is DETERMINISTIC (regex/keyword) — no local LLM.
- Every external failure surfaces as a plain-language message, never a
  traceback, never a silent lie.
