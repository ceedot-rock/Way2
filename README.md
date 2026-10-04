# Way2

Hands-free smart GPS for people who drive for work.

You talk, it drives the conversation: say where you're starting from and
where you're headed, and it routes you on open map data, warns you about
weather on your route, reports live traffic, and tells you when a faster
way exists — all without touching the screen. Built for my coworkers, who
spend their days driving between job sites.

```
you> starting from Cherry Hill, NJ
way2> Got it — starting from Cherry Hill Township.
you> navigate to Philadelphia, PA
way2> Destination set: Philadelphia. 8.4 miles, about 16 minutes of driving.
you> what's my ETA
way2> About 16 minutes — arriving around 5:20 PM.
you> weather along the route
way2> Weather on your route:
- Light rain near your starting point — roads may be slick.
- Light rain along the way — roads may be slick.
- Light rain near your destination — roads may be slick.
you> traffic on my route
way2> Heavy traffic on 2 of 8 segments, about 1 min of delay
- Jam: Slow traffic
- Road Works: Roadworks
you> any faster route
way2> You're already on the fastest route I can see.
Live traffic: about 2 min of delay on your route. Jam: Slow traffic Road Works: Roadworks
```

## Try it

```bash
python3 -m way2.app            # text mode (easiest demo)
python3 -m way2.app --say      # text in, spoken responses out
python3 -m way2.app --voice    # voice in + voice out (needs mic + whisper)
```

For live traffic, set a free TomTom key first (developer.tomtom.com):

```bash
export TOMTOM_API_KEY=your_key_here
```

Things to say: `starting from …`, `navigate to …`, `add a stop in …`,
`skip the next stop`, `what's my ETA`, `trip summary`,
`find restaurants` / `find scenic spots`, `weather along the route`,
`traffic on my route`, `any faster route`, `help`, `quit`.

## How it's built

| Piece | Tech | What it does |
|---|---|---|
| Geocoding + places | OpenStreetMap via Nominatim (free, no key) | turns "Cherry Hill" into coordinates; finds restaurants, scenic spots |
| Routing | OSRM (public demo server, free, no key) | driving routes, turn-by-turn steps, alternative routes |
| Weather | Open-Meteo (free, no key) | current conditions sampled along the route |
| Live traffic | TomTom Traffic API (free key) | flow speeds + incidents on your route; feeds "any faster route" |
| Speech in/out | Whisper (local) + TTS | transcribe commands, speak responses — offline |
| Command parsing | regex/keyword (this repo) | deterministic intent parsing, no LLM |

Two builders, one repo — see [docs/CONTRACT.md](docs/CONTRACT.md) for who
owns what. The short version:

- `way2/trip.py` — trip state + deterministic `parse_command`
- `way2/weather.py` — `alerts_along_route` via Open-Meteo
- `way2/geo.py` — Nominatim geocoding/places, OSRM routing
- `way2/traffic.py` — live flow speeds + incidents via TomTom
- `way2/voice.py` — local Whisper transcription, mic, TTS
- `way2/app.py` — the conversation loop

## What's live, what's next

Live: routing with turn-by-turn steps, on-demand rerouting ("skip the next
stop", "any faster route"), weather alerts along the route, live traffic
via TomTom (needs a free key), spoken I/O.

Honest note: without a TomTom key the app says so out loud and sticks to
the road network for "faster route" — it won't fake traffic data it doesn't
have.

What's next: saved home/work spots, low-bridge warnings for the box
trucks.

## Tests

```bash
python3 -m unittest discover -s tests
```

113 tests, all green. Unit tests mock all HTTP; `tests/test_live.py` runs a
small number of real requests against Nominatim, OSRM, and Open-Meteo
(free, no-key APIs) as a smoke check. The TomTom integration is verified
against the real API with real route data.

## Privacy

Your voice is transcribed on your own machine by Whisper. Map and weather
lookups go to public open-data services (that's how any map works); traffic
lookups go to TomTom. There's no account, no tracking SDK, no ad profile —
nothing to sign into, nothing that knows who you are.

## License

Apache-2.0. See [LICENSE](LICENSE).
