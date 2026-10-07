# Security Policy

Way2 talks to public map, weather, and traffic services and listens on a
microphone. A bug that leaks the driver's location, sends audio anywhere
except local Whisper, or silently uses fabricated traffic/weather as if it
were real is a security issue, not a normal bug.

## Reporting a vulnerability

Please do not open a public issue for security problems.

- Use GitHub's private vulnerability reporting on this repository
  (Security tab, "Report a vulnerability")
- Or email: corey@slidphilabs.com with the subject line `Way2 security`

Include the affected file, steps or inputs to reproduce, and what you
expected versus what happened.

You can expect an acknowledgement within 3 business days. We will keep you
updated while we investigate and credit you in the changelog unless you
prefer to stay anonymous.

## In scope

- Location data leaving the machine to somewhere the README doesn't name
- Audio leaving the machine instead of being transcribed by local Whisper
- Traffic or weather presented as real when no real source was consulted
- API keys, tokens, or credentials ending up in commits or logs
- Unsafe handling of the microphone or speaker devices

## Out of scope

- Nominatim / OSRM / Open-Meteo / TomTom being down or rate-limiting
  (their public demo servers are free and rate-limited by design)
- Social engineering, spam, or denial-of-service against those services
