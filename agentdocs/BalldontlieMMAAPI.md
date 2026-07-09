# BallDontLie MMA API Notes (verified 2026-07)

Base URL `https://api.balldontlie.io/mma/v1`. Auth: the API key goes RAW in
the `Authorization` header (NOT `Bearer <key>`). List endpoints return
`{"data": [...], "meta": {...}}`.

| Endpoint | Tier | Used for |
|---|---|---|
| `/events?year=&date=` | free | Card discovery (name, date, `main_card_start_time`, `promotion`) |
| `/fights?event_ids[]=` | GOAT (paid) | Per-fight matchups + status |
| `/fight_stats?fight_ids[]=` | GOAT (paid) | Per-fighter live aggregates (sig strikes, takedowns, knockdowns, control time) |

- Plan gating shows up as **HTTP 401/403 on the endpoint**, not a stubbed
  response — the client maps those to `[]` and logs, so the product degrades
  to schedule-only instead of crashing.
- Event names look like `"UFC 329: McGregor vs. Holloway 2"` — the matchup is
  the part after `": "`; `promotion.name` filters UFC vs PFL etc.
- Live stat polling is enabled by `BALLDONTLIE_GOAT_TIER=1` **and** a plan
  that actually unlocks the endpoints; verify with a curl before fight night.
