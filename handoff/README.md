# AgentPredict — Project Handoff

Written 2026-07-08 (updated same day for the production build-out). This directory
is the **current-state** snapshot of the project — everything needed to pick the
work back up. (The older `agentdocs/` are the original June-3 skeleton specs and
are stale; trust these files where they disagree.)

- **[ARCHITECTURE.md](ARCHITECTURE.md)** — how the system fits together, the data
  contracts, and the non-obvious constraints that shaped the design.
- **[RUNBOOK.md](RUNBOOK.md)** — how to build, run, test, debug, and switch between
  mock and real modes on this machine.
- **[DEPLOY.md](DEPLOY.md)** — hosting the production stack at agentpredictmma.com.

## Production build-out (2026-07-08)

The stack is now a **final product** aimed at agentpredictmma.com:

- **Polymarket discovery is events-by-tag**: `/events?tag_slug=ufc` → one Market
  per listed fight (the winner moneyline), carrying matchup `title`, `card_title`
  ("UFC 329"), `fight_info` ("Welterweight · Main Card"), and `volume`. Futures
  ("champion at end of 2026", "who fights next") are rejected by title shape;
  stale leftovers (started >12h ago, never closed) are dropped. UFC 329 (Jul 11,
  Holloway vs. McGregor 2 + 14 more fights) flows end-to-end with real odds and
  week-long price histories.
- **Wire contract**: `MarketEvent` fields 9–13 = title/card_title/fight_info/volume/event_slug;
  `outcome` is now ONE fighter's name (probability = that fighter's win prob);
  the matchup lives in `title`. The dashboard renders matchups, groups upcoming
  fights by card, and headlines the highest-volume market of the soonest card.
- **RAG is production-gated**: per-market cooldown (`RAG_MARKET_COOLDOWN_S`=90),
  single-flight inference in a worker thread (async engine stream), hourly
  Pinecone upsert budget, Gemini safety-block handling, percent-confidence
  parsing, token-based verifier (surnames pass), and only PASSED verifications
  are broadcast. Retrieval queries use the full fight description.
- **Gateway is hardened**: honest `/health` (503 + reasons when a subscriber is
  down or the engine stream is silent), gRPC keepalives everywhere, `/ws` origin
  allowlist (`GATEWAY_ALLOWED_ORIGINS`) + client cap, concurrent fan-out with
  one serialization per message, dead sockets actively closed.
- **Production packaging**: `dashboard/Dockerfile` (static Vite build + nginx
  serving the SPA and proxying `/ws`+`/health` to the gateway — single origin,
  auto `wss://`), `docker-compose.prod.yml` (only :80 public, restart: always),
  `scripts/run-stack.sh prod` (nginx on :8080 for rootless podman).

---

## What AgentPredict is

A real-time UFC prediction dashboard. It fuses **Polymarket betting odds** with
**live fight statistics** (BallDontLie MMA API), streams both through a C++ event
engine, and uses an agentic **RAG layer** (Pinecone + Gemini) to generate plain-English
explanations of *why* the odds are moving. The product story is a fight-card
lifecycle: browse **upcoming** fights up to a week+ out (countdowns + a week of odds
history), then when a fight goes **live**, watch odds swing alongside a play-by-play
of strikes/takedowns/knockdowns.

## Current status (2026-07-08, post build-out)

- **The final product runs on REAL data end-to-end** — no mock anywhere in the
  serving path (mock mode remains for offline demos/tests).
- **Branch:** `samad` (commits are made here, not `main`; **not pushed** — Samad
  decides when to push).
- **The stack is RUNNING in REAL mode**: dashboard on `localhost:5173`, gateway
  on `localhost:8000`. From a laptop:
  `ssh -N -L 5173:localhost:5173 -L 8000:localhost:8000 samad@100.91.26.104`
- **Test baseline (all green):** 47 C++ engine tests, 109 Python tests
  (agents + rag + gateway), 42 dashboard vitest tests, `tsc` clean.
- **Verified live against real APIs (2026-07-08):** 27 Polymarket fight markets
  (all 15 UFC 329 fights incl. Holloway–McGregor at $2.0M volume, 12 UFC Fight
  Night fights), every one with matchup/card/segment metadata and a 57-point
  week-long price history; 6 upcoming cards from BallDontLie; a real
  Gemini+Pinecone prediction generated, verified, and delivered over the WS
  (grounded and honest — it declined to invent a cause for a quiet-market move);
  the production nginx image serving the SPA and proxying /ws + /health.
- **Known API drift handled:** Gamma's bare `/events` and `/markets` are marked
  deprecated (Sunset already passed) — fight discovery uses `/events/pagination`;
  CLOB `prices-history` now requires `fidelity` (≥5 min for the 1w range).

## Decisions Samad has made (don't re-litigate)

1. **No BallDontLie tier upgrade for now.** `/fights` and `/fight_stats` are 401
   (plan-gated, GOAT tier ~$39.99/mo). Live round-by-round stats stay dormant in
   real mode until he upgrades; the UI is built to light up automatically when
   `BALLDONTLIE_GOAT_TIER=1` and the key allows it.
2. **UFC only.** Promotion filter stays `MMA_PROMOTION=UFC`; the Polymarket
   off-theme fallback stays off (`POLYMARKET_FALLBACK_ALL=0`).
3. **Working style:** broad autonomy granted ("finish the project"), build with
   mocks first and connect real APIs at the end, never paste API keys in chat
   (`.env` is gitignored and must stay uncommitted).

## Real-data reality (verified against live APIs)

- **BallDontLie MMA:** `/events` works on Samad's key and returns real UFC cards.
  `/fights` and `/fight_stats` → HTTP 401 on his plan. So real mode discovers
  upcoming cards from `/events` and emits `FIGHT_UPCOMING` sentinels; per-fight
  live stats need the tier upgrade.
- **Polymarket:** UFC fight markets typically list only **close to the event** —
  on most days there are zero live UFC markets (politics/World Cup dominate the
  active list). The dashboard shows honest placeholders ("odds not yet listed")
  until markets appear, then merges them with the BallDontLie schedule.

## Likely next steps (nothing is in-flight)

- **Host it**: follow [DEPLOY.md](DEPLOY.md) — DNS for agentpredictmma.com, TLS
  in front, `docker-compose.prod.yml` (or `scripts/run-stack.sh prod` here).
- **UFC 329 fight night (Jul 11)** is the natural live validation: phases flip
  `upcoming → live`, odds swing, RAG explains them (cooldown-gated, one
  explanation per market per 90s).
- If Samad upgrades BallDontLie to GOAT tier: set `BALLDONTLIE_GOAT_TIER=1` in
  `.env` — live stats polling and the Live Fight Tracker light up with no code
  changes (mock mode already exercises that whole path).
- Push `samad` branch / open a PR to `main` — only when Samad asks.
