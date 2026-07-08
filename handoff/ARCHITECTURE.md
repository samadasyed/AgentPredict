# Architecture & Constraints

The pipeline, the data contracts, and the non-obvious rules that shaped them.
Violating any constraint in this file has already caused a real bug at least once.

## Pipeline

```
Polymarket (Gamma + CLOB APIs)          BallDontLie MMA API
        │                                       │
        ▼                                       ▼
 agents/polymarket/agent.py             agents/mma/agent.py
        │        gRPC IngestService (proto/events.proto)
        └────────────────┬──────────────────────┘
                         ▼
              C++20 engine (engine/)
        Normalizer → ring-buffer EventStore
                         │ gRPC EventStream.Subscribe
            ┌────────────┴─────────────┐
            ▼                          ▼
  rag/orchestrator.py         gateway/ (FastAPI)
  context → retrieve →                │
  Gemini → verify                     │
            │ gRPC RagStream          │
            └───────────► gateway ────┤
                                      ▼ WebSocket /ws (two message kinds:
                                        canonical events + rag predictions)
                            dashboard/ (React + Vite + Tailwind)
```

- Each box is a container: `ap-pm`, `ap-mma`, `ap-engine`, `ap-rag`, `ap-gateway`,
  `ap-dash` on the `agentpredict_net` podman network (see RUNBOOK).
- `MOCK_MODE=1` swaps the API clients (`agents/*/mock_client.py`) and the RAG
  retriever/inference (`rag/mock_components.py`) for offline synthetic versions —
  the engine, gateway, and dashboard run the exact same code in both modes.

## The fight-card lifecycle (the product model)

Every fight/market has a phase: **`upcoming` → `live` → `final`**, carried on both
`MarketEvent.phase` and `FightStatEvent.phase`, alongside `event_start` (ms epoch).
The dashboard derives the whole UI from this:

- **Upcoming:** countdown chips (`formatCountdown`), a week of odds history as a
  sparkline/trend chart, "odds not yet listed" placeholder when only the schedule
  (BallDontLie) knows about the fight.
- **Live:** pulsing LIVE hero, harder-swinging odds, Live Fight Tracker
  (scoreboard + play-by-play) fed by `FightStatEvent`s.
- Market ⟷ fight fusion is by **shared fighter surname** (`findFightForOutcome`,
  `sameMatchup`) — which is why mock market outcomes ("A def. B") and mock fight
  names must use identical fighter names.

## Hard constraints (each one caused a bug when missed)

### 1. Engine 60-second clock-skew guard → history rides as a snapshot
`engine/src/normalizer.cpp` `ValidateTimestamp` rejects any event whose envelope
`timestamp` deviates more than 60s from now (`kMaxClockSkewMs`). **You cannot
stream a week of odds history as back-dated events.** Instead, `MarketEvent`
carries `repeated ProbabilityPoint history` — days-old points inside a now-dated
event pass fine. Only the envelope timestamp is skew-checked.

### 2. Sentinel stat_types are not stats
`FIGHT_UPCOMING` and `FIGHT_DISCOVERED` are schedule/discovery markers that are
**re-emitted every poll** (so late-joining clients see the card). They must be
excluded everywhere a real stat would be aggregated or reacted to:
- dashboard: `SENTINEL_STATS` set in `dashboard/src/lib/marketSeries.ts` (gates
  `isStat`, hence `buildLiveFights` / `buildFightUpdates`) and the EventFeed filter.
- RAG: `_SENTINEL_STATS` in `rag/orchestrator.py::_is_meaningful` — without it,
  re-emitted sentinels spam Gemini with nonsense predictions every 30s.
If you add a new sentinel, add it to **both** sets and the proto comment.

### 3. protobuf int64 → JSON strings
The gateway converts protos with `MessageToDict` (centralized in
`gateway/proto_utils.py::to_dict` — the protobuf-5 kwarg is
`always_print_fields_with_no_presence`, the old kwarg was removed and silently
killed the data plane once). int64 fields (`timestamp`, `event_start`, history
timestamps) arrive in the browser as **strings**; the dashboard coerces with the
`num()` helper in `marketSeries.ts`. Any new int64 field needs the same coercion.

### 4. Snapshot-on-first-sight
The Polymarket agent emits a **baseline event (delta 0)** the first time it sees a
market — otherwise static pre-event markets never appear (the old behavior emitted
only on |delta| ≥ threshold, leaving the dashboard empty on quiet days). RAG
ignores |delta| < 0.02, so baselines don't trigger predictions.

### 5. Proto changes ripple three ways
Editing `proto/events.proto` requires regenerating: (a) Python stubs in
`agents/generated/` (checked in — see RUNBOOK for the container recipe + the sed
import fix), (b) C++ stubs (automatic at engine image build), (c) TypeScript
mirror types in `dashboard/src/types/events.ts` (manual).

## Key files by concern

| Concern | Files |
|---|---|
| Wire contract | `proto/events.proto` (ProbabilityPoint, MarketEvent.history/event_start/phase, FightStatEvent.event_start/phase, sentinel docs) |
| Odds polling + history | `agents/polymarket/client.py` (Gamma markets, CLOB `/prices-history?interval=1w`, browser UA), `agent.py` (QUERY filter, FALLBACK_ALL, baseline emit), `models.py` |
| Card discovery + live stats | `agents/mma/client.py`, `agent.py` (`_poll_upcoming`, `_event_phase`, `_event_matchup`, promotion/window filter), `models.py` |
| Demo data | `agents/polymarket/mock_client.py` + `agents/mma/mock_client.py` — a matched 5-fight card (Jones/Aspinall **live**, then Makhachev +6h, Pereira +2d, O'Malley +5d, Topuria +9d). Mock questions must contain "UFC" to pass the QUERY filter |
| Engine | `engine/src/normalizer.cpp` (validation, skew guard), `event_store.*` (ring buffer), `grpc_server.*` |
| RAG | `rag/orchestrator.py` (`_is_meaningful`, RagStream fan-out), `context_builder.py`, `retriever.py`, `inference.py`, `verifier.py`, `mock_components.py` |
| Gateway | `gateway/proto_utils.py` (the one MessageToDict call site), WS fan-out in `gateway/` |
| Dashboard view-model | `dashboard/src/lib/marketSeries.ts` (buildMarketSeries, pickFeatured, phases, sentinels, num()), `lib/fights.ts` (buildUpcomingFights merge) |
| Dashboard UI | `components/featured/FeaturedFight.tsx` (phase-aware hero), `components/live/LiveFightTracker.tsx` + `statLabels.ts`, `components/upcoming/UpcomingFights.tsx` + `UpcomingFightHero.tsx`, `components/events/EventFeed.tsx`, `App.tsx` (hero priority: live/featured market → soonest upcoming fight → waiting box) |
| Tests worth knowing | `dashboard/src/tests/lib/*.test.ts` (sentinel regression), `agents/tests/unit/*` (baseline-emit contract, upcoming filters), `rag/tests/unit/test_orchestrator.py` (sentinel skip), `gateway/tests/unit/test_proto_utils.py` (protobuf-bump canary) |

## Environment knobs (beyond `.env.example`)

| Var | Default | Meaning |
|---|---|---|
| `POLYMARKET_QUERY` | `UFC` | Keep only markets whose question contains this. Blank = all live markets |
| `POLYMARKET_FALLBACK_ALL` | `0` | If `1`, fall back to all live markets when the query matches none (off by default so a UFC view stays clean) |
| `POLYMARKET_HISTORY_INTERVAL` | `1w` | CLOB prices-history window for the trend chart |
| `MMA_PROMOTION` | `UFC` | Upcoming-card promotion filter |
| `MMA_UPCOMING_DAYS` | `45` | Discovery window (now−24h … now+N days) |
| `MMA_UPCOMING_MAX` | `12` | Cap on tracked upcoming cards |
| `MMA_UPCOMING_REFRESH_S` | `600` | How often to re-fetch the schedule |
| `BALLDONTLIE_GOAT_TIER` | `0` | `1` enables live `/fight_stats` polling (needs paid tier in real mode; mock stack sets it) |
