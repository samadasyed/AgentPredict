# Component: `dashboard/` + `gateway/` — the web surface

## Gateway (`gateway/`, FastAPI)

- **`/ws`** — the only data feed. JSON envelopes `{"type":"event"|"prediction",
  "data":…}`. Origin allowlist (`GATEWAY_ALLOWED_ORIGINS`; browsers from
  other sites rejected, no-Origin clients like curl allowed), client cap,
  oversized-frame guard. Per-client source filter via
  `{"action":"filter","source":"pm"|"mma"|"all"}`.
- **Broadcaster** — 200-message replay buffers per stream (late joiners get
  recent history), serialize-once + concurrent fan-out, dead sockets actively
  closed so browsers reconnect instead of freezing.
- **Subscribers** — gRPC consumers of the engine and RAG streams with
  keepalive options and health state; **`/health` returns 503 with reasons**
  when a subscriber is down or the engine stream is silent >180 s.
- **`proto_utils.to_dict`** — the single proto→JSON call site.
  ⚠ protobuf int64 fields become JSON **strings**; the dashboard must
  `Number()`-coerce anything time- or count-like.

## Dashboard (`dashboard/`, React + Vite + Tailwind)

View-model logic is concentrated in two libs — components mostly render:

- **`src/lib/marketSeries.ts`** — builds per-market series from the event
  list (seeds points from the richest `history` snapshot, appends live
  ticks), phase classification, hero selection (live first, else soonest
  card's highest-volume market), live-fight aggregation (scoreboard +
  play-by-play, sentinels excluded), matchup/URL helpers.
- **`src/lib/fights.ts`** — merges schedule sentinels with market series into
  the upcoming-fight list (surname matching), card billing order
  (`segmentRank`: Main Card → Prelims → Early Prelims).

Components: `featured/` (phase-aware hero + odds bar + trend chart),
`upcoming/` (card-grouped fight grid, countdowns, sparklines, Polymarket
links), `live/` (fight tracker), `events/` + `predictions/` (the two feed
panels, each with an InfoHint explainer), `shared/` (InfoHint popover,
PolymarketLink).

`src/hooks/useEventStream.ts` — WS lifecycle: reconnect w/ 3s delay, dedup by
event id (replays), bounded arrays, WS URL derived from `location` in prod
(`wss://<host>/ws`) with a `VITE_GATEWAY_WS_URL` override for dev.

## Images

- `Dockerfile.dev` — Vite dev server (:5173).
- `Dockerfile` — production: static build served by nginx which also proxies
  `/ws` + `/health` to the gateway (single origin). The nginx config is a
  template with a **dynamic resolver** so a recreated gateway container (new
  IP) keeps working without an nginx restart.

## Tests

`src/tests/` — vitest for both libs and feed components + `tsc --noEmit`.
