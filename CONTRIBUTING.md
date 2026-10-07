# Contributing to Way2

Thanks for helping build hands-free GPS for people who drive for work.

## Ground rules

- The app never fabricates data. If a TomTom key is missing, the app says
  so out loud and falls back to the road network — it never invents
  traffic or weather. A PR that makes traffic look real without a real
  source will not be accepted.
- Command parsing stays deterministic (regex/keyword in `way2/trip.py`).
  No LLM on the parse path.
- Voice transcription stays local (Whisper on the driver's own machine).
  No sending audio to third-party services.

## Quick checks

```sh
python3 -m unittest \
  tests.test_alerts tests.test_app tests.test_geo tests.test_traffic \
  tests.test_trip tests.test_voice tests.test_weather
```

All HTTP is mocked in the unit tests, so they run in milliseconds with no
keys. CI runs these plus a committed-secrets scan on every pull request.

## Live smoke (local only)

```sh
python3 -m unittest tests.test_live
```

This makes a small number of real requests against the free, no-key
services (Nominatim, OSRM, Open-Meteo). Run it before a PR that touches
`way2/geo.py`, `way2/weather.py`, or `way2/traffic.py`. It is not run in
CI, out of politeness to the public APIs.

## Opening a pull request

Use the PR template. Keep the diff small, keep the voice honest, and make
sure no API keys or credentials end up in the commit.

## Licensing

Way2 is Apache-2.0 (see LICENSE). By contributing you agree your
contribution may be distributed under that license.
