# Way2: hands-free GPS for the people who drive for work

*DEV Hacktoberfest Weekend Challenge submission — "Build for a Friend"*

## Who it's for

My coworkers. Most of them spend the day driving between job sites — gutters don't install themselves, and the van is always going somewhere. They've all got a phone mount and a GPS app, but every one of those apps wants an account, wants your location history, and wants you tapping a screen at 60 miles an hour. I wanted to build them something simpler: you talk, it handles the driving conversation. No account. No tapping.

So that's what Way2 is. You say "starting from Cherry Hill, navigate to Philadelphia," and it routes you. "What's my ETA." "Weather along the route." "Traffic on my route." "Any faster route." "Find restaurants." It answers out loud, like a copilot riding shotgun who actually looked at the map.

## What I built

A Python app with a conversation loop. Underneath it's seven small modules, and every piece that matters is open:

- **OpenStreetMap (Nominatim)** — turns "Cherry Hill" into coordinates, and finds restaurants and rest-worthy spots near the route. Free, no key.
- **OSRM** — driving routes with turn-by-turn steps, plus alternative routes when you ask for a faster way. Free, no key.
- **Open-Meteo** — current weather sampled at points along your route, so it can tell you about the rain before you're in it. Free, no key.
- **TomTom Traffic** — live flow speeds and incidents on your route. This is the one piece that needs a key, and it's free at developer.tomtom.com. Ask "traffic on my route" and it tells you the delays; ask "any faster route" and the live traffic feeds the answer.
- **Whisper** — speech-to-text running on your own machine, so your voice never goes to a server. Verified end-to-end: it transcribed a real spoken command word-for-word.
- **Deterministic command parsing** — regex and keywords, no LLM. When you're driving, "skip the next stop" should do the same thing every time. It does.

Two of us built it in a weekend in one repo, split down the middle by a contract file: one side owns geo/voice/app/traffic, the other owns the trip intelligence (parsing, weather alerts, faster-route checks). The contract is in the repo if you're curious how that worked.

## Demo

Real run, real APIs, this evening — Cherry Hill, NJ to Philadelphia, PA:

```
you> starting from Cherry Hill, NJ
way2> Got it — starting from Cherry Hill Township.
you> navigate to Philadelphia, PA
way2> Destination set: Philadelphia. 8.4 miles, about 16 minutes of driving.
you> traffic on my route
way2> Heavy traffic on 2 of 8 segments, about 1 min of delay
- Jam: Slow traffic
- Road Works: Roadworks
you> any faster route
way2> You're already on the fastest route I can see.
Live traffic: about 2 min of delay on your route. Jam: Slow traffic Road Works: Roadworks
```

That traffic was real — TomTom's live feed, sampled at points along the actual route geometry.

`python3 -m way2.app` runs it in text mode. `--voice` gives you mic in and spoken answers out. 113 tests, all green; the unit tests mock all HTTP, and the live ones hit the real map, weather, and traffic APIs so we know the whole chain works, not just the mocks.

## Why open innovation matters for this build

Here's the honest version: this app only exists because the open pieces exist.

A hands-free GPS for a crew of drivers is not a venture-scale idea. Nobody is funding it. If every piece had needed a commercial API key, a billing account, and a terms-of-service review, it would never have gotten past Saturday morning. Instead: Nominatim geocoded every address, OSRM routed every mile, Open-Meteo reported the actual rain, Whisper transcribed without phoning home — all free, all without asking anyone's permission. TomTom's free tier closed the last gap: real-time traffic, the one thing with no good open source, for zero dollars. The whole thing cost nothing and needs one free key. That's not a philosophy, that's just how the weekend went.

And it changes what the app *is*. Because there's no account, there's no location history sitting on somebody's server — the privacy isn't a feature we added, it's what falls out of having no server. Because the map data is OpenStreetMap, a driver in a small town gets the same quality as a driver in a big city; nobody's deciding which places are worth covering. Because the models and code are open, when my coworker says "it'd be nice if it warned me about low bridges," that's a weekend project, not a feature request into a void.

One honest line: without the TomTom key the app tells you so and sticks to the road network. It won't fake traffic data it doesn't have. I'd rather have that sentence in the product than a traffic feature I can't build honestly.

## What's next

Saved home/work spots. Low-bridge warnings for the box trucks. Then I'm handing the repo to the crew and seeing what they complain about first — that's the real roadmap.

Repo: https://github.com/ceedot-rock/Way2

*Built for the DEV Hacktoberfest Weekend Challenge. Apache-2.0.*
