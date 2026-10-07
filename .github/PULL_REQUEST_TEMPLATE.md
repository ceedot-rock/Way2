## What changed

<!-- One or two sentences. -->

## Modules touched

<!-- e.g. way2/geo.py, way2/weather.py, or "none" -->

## Checks

- [ ] Unit tests pass (`python3 -m unittest tests.test_alerts tests.test_app tests.test_geo tests.test_traffic tests.test_trip tests.test_voice tests.test_weather`)
- [ ] Live smoke (`python3 -m unittest tests.test_live`) passes, if `geo.py`, `weather.py`, or `traffic.py` changed
- [ ] No fake data: traffic or weather is never fabricated — if a key is missing, the app says so
- [ ] No secrets committed (no API keys, tokens, or credentials in the diff)
