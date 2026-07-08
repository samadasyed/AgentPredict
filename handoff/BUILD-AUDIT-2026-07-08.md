# Build Audit — Production Build-Out (2026-07-08)

Autopilot session summary: AgentPredict was taken from "works with real UFC
events" to the **final product** now branded **AgentPredict MMA**, targeting
**agentpredictmma.com**. Commits `2794997` (build-out) and the follow-up rebrand
commit on the `samad` branch. The stack is running live in real mode.

## What exists now

A real-time MMA prediction site running on **100% real data** — no mock
anywhere in the serving path (mock mode remains for offline demos/tests):

- Every fight Polymarket lists (15 UFC 329 fights including the $2M
  Holloway–McGregor main event, 12 more on the following week's card), each
  with live odds, matchup/card/segment metadata, and a real week-long price
  history (57 points).
- Cards Polymarket hasn't priced yet come from BallDontLie with countdowns and
  honest "odds not yet listed" placeholders.
- AI predictions (Gemini + Pinecone) that explain odds moves, verified before
  display.

## Audit of decisions and changes

**1. Real fight data, done properly.** Discovery switched from "top-volume
markets containing 'UFC'" to Gamma **events-by-tag**: one market per listed
fight carrying the matchup (`title`), card (`card_title`), weight class/segment
(`fight_info`), and `volume`. Futures ("champion at end of 2026", "who fights
next") are rejected by title shape; stale leftovers from card changes are
dropped. The wire contract changed: `outcome` is one fighter's name and
`probability` is their win probability.

**2. Two live API-drift bugs found and fixed.** CLOB price history now requires
a `fidelity` parameter (histories were silently empty without it), and Gamma's
bare `/events` is deprecated with an already-passed Sunset header — discovery
moved to `/events/pagination` before the old endpoint disappears.

**3. AI predictions verified for real.** A real-shaped odds move was injected
and a real Gemini + Pinecone prediction flowed to the browser — grounded, named
the fighters, and honestly declined to invent a cause for a quiet-market move.
The RAG loop is production-gated: one explanation per market per 90s
(`RAG_MARKET_COOLDOWN_S`), single-flight inference in a worker thread, hourly
Pinecone write budget, Gemini safety-block handling, percent-confidence
normalization, and failed verifications are logged instead of shown.

**4. Hardened for public hosting** (multi-agent production audit confirmed the
gaps before fixing): `/health` reports real data-plane state (503 when a stream
dies — previously it stayed green through a dead feed), gRPC keepalives on every
channel, WebSocket origin allowlist + connection cap + frame-size guard,
serialize-once concurrent fan-out, dead sockets actively closed, and a
background-task watchdog. Quiet markets re-baseline every 120s so fresh browser
tabs always see the full slate (replay buffer deepened to match).

**5. Ready for agentpredictmma.com.** Production dashboard image (static Vite
build + nginx serving the site and proxying `/ws` + `/health` on one origin so
`wss://` just works behind TLS), `docker-compose.prod.yml` (only port 80
public, `restart: always`), `scripts/run-stack.sh prod`, and a step-by-step
deployment guide in `handoff/DEPLOY.md`.

**6. Rebrand: UFC → MMA.** All site branding and copy now say **AgentPredict
MMA** (header, page title, meta description); the deployment target and origin
allowlist are `agentpredictmma.com`. Event names arriving from Polymarket's
data feed (e.g. "UFC 329: …") are shown as-is — they are factual references to
third-party event names (the same nominative use every odds/news site relies
on), not our branding.

## Test baseline (all green)

| Suite | Count |
|---|---|
| C++ engine (GTest, in-container) | 47 |
| Python (agents + rag + gateway) | 109 |
| Dashboard (vitest) + `tsc` | 42 |

## Known limits / standing decisions

- **Live round-by-round stats** stay dormant until BallDontLie is upgraded to
  GOAT tier (`/fights` + `/fight_stats` are 401 on the current plan). Odds,
  countdowns, trends, and AI predictions all work without it; the Live Fight
  Tracker lights up automatically once `BALLDONTLIE_GOAT_TIER=1` and the plan
  allows it.
- Coverage is UFC-promotion fights only by configuration (`POLYMARKET_TAG=ufc`,
  `MMA_PROMOTION=UFC`) — widen both to cover PFL etc. later if desired.
- Branch `samad`, not pushed; Samad decides when to push/PR.
