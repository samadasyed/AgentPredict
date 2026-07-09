# AgentPredict MMA

**Live MMA odds, fight stats, and AI explanations of why the lines move.**

AgentPredict streams every fight market Polymarket lists — real odds, week-long
price trends, countdowns, full card structure — and, during live events, fuses
in round-by-round fight statistics. An agentic RAG pipeline (vector retrieval +
LLM + verification) watches the odds and publishes short, grounded explanations
whenever a fight's line makes a real move.

> Live deployment: **https://agentpredictmma.com**

## Features

- **Every listed fight, automatically** — discovery via Polymarket's tagged
  events API: one card per fight with matchup, weight class, card segment
  (Main Card / Prelims / Early Prelims), volume, and a link to the market.
- **Real price history** — 7-day odds trend per fight from the CLOB
  price-history API, seeded instantly on page load.
- **Fight-card lifecycle** — `upcoming → live → final`: countdowns before,
  live-swinging odds and a play-by-play scoreboard during (stats plan
  permitting), honest placeholders when data isn't available yet.
- **AI analysis with guardrails** — explanations trigger on *cumulative* odds
  drift (≥2 pts since last analysis), are grounded in retrieved evidence,
  and pass a verification gate (confidence + must reference the fighters)
  before anyone sees them. Cost-capped by per-market cooldowns and write
  budgets.
- **Production-hardened plumbing** — honest `/health` (503 when the data plane
  degrades), gRPC keepalives, WebSocket origin allowlist, replay buffers for
  late-joining clients, single-origin nginx serving the SPA and proxying the
  data plane.

## Architecture

```
Polymarket (Gamma + CLOB)              BallDontLie MMA API
        │                                       │
        ▼                                       ▼
 Python polling agent                   Python polling agent
        │        gRPC IngestService (proto/events.proto)
        └────────────────┬──────────────────────┘
                         ▼
              C++20 engine  ── validation (Normalizer)
                         │  ── ring-buffer EventStore
                         │ gRPC EventStream
            ┌────────────┴─────────────┐
            ▼                          ▼
   RAG orchestrator            FastAPI gateway
   (Pinecone + Gemini)                 │
            │ gRPC RagStream           │
            └───────────► gateway ─────┤
                                       ▼ WebSocket /ws
                             React dashboard (Vite + Tailwind)
```

Each box is a container. In production only the dashboard's nginx (port 80) is
public — it serves the static build and proxies `/ws` + `/health` to the
gateway on the internal network.

## Quickstart — no API keys needed

Runs the whole stack on synthetic data (a full demo fight card with a live
main event, moving odds, play-by-play, and AI predictions):

```bash
make demo          # docker compose or podman; falls back to scripts/run-stack.sh mock
# → dashboard at http://localhost:5173
```

## Real data

```bash
cp .env.example .env    # then fill in your keys
make up                 # or scripts/run-stack.sh real
```

| Provider | Used for | Key |
|---|---|---|
| Polymarket (Gamma + CLOB) | Odds, markets, price history | none needed |
| [BallDontLie MMA](https://www.balldontlie.io) | Card schedule (free tier); live round-by-round stats (GOAT tier) | `BALLDONTLIE_API_KEY` |
| Google Gemini | Explanation generation + embeddings | `GOOGLE_API_KEY` |
| [Pinecone](https://www.pinecone.io) | Evidence vector store | `PINECONE_API_KEY` |

Everything degrades gracefully: no listed markets → schedule-only cards with
"odds not yet listed"; no stats tier → odds-only live view; no RAG keys → the
rag service exits and the rest keeps running.

## Production

`docker compose -f docker-compose.prod.yml up -d --build` — or, with no public
IP, publish straight through a Cloudflare Tunnel. Full click-by-click guide:
[handoff/DEPLOY.md](handoff/DEPLOY.md).

## Tests

```bash
# Python (agents + rag + gateway)
PINECONE_API_KEY=fake GOOGLE_API_KEY=fake PINECONE_INDEX_NAME=agentpredict \
  pytest agents/tests/unit rag/tests/unit gateway/tests/unit

# C++ engine (inside the engine container/build)
cmake --build engine/build --target engine_unit_tests && ctest --test-dir engine/build

# Dashboard
cd dashboard && npx vitest run && npx tsc --noEmit
```

Suite sizes at last count: 47 C++ · 112 Python · 44 dashboard, `tsc` clean.

## Repository layout

| Path | What it is |
|---|---|
| `proto/` | The single wire contract (`events.proto`) every service shares |
| `agents/` | Python pollers: Polymarket odds + BallDontLie schedule/stats |
| `engine/` | C++20 validation + ring-buffer event store, gRPC in/out |
| `rag/` | Orchestrator, Gemini inference, Pinecone retriever, verifier |
| `gateway/` | FastAPI WebSocket fan-out with health, origin allowlist, replay |
| `dashboard/` | React/Vite/Tailwind SPA + production nginx image |
| `agentdocs/` | Per-component reference docs |
| `humandocs/` | Narrative overview for humans new to the project |
| `handoff/` | Operational docs: architecture constraints, runbook, deployment |
| `scripts/` | Stack launcher (mock/real/prod), stream watcher, screenshot tool |

## Docs

- New to the project? Start with [humandocs/ProjectOverview.md](humandocs/ProjectOverview.md).
- Hacking on a component? Its file in [agentdocs/](agentdocs/) is the reference.
- Running or deploying it? [handoff/RUNBOOK.md](handoff/RUNBOOK.md) and
  [handoff/DEPLOY.md](handoff/DEPLOY.md).
- The non-obvious design constraints (clock-skew guard, sentinel events,
  int64-as-strings, cost guards): [handoff/ARCHITECTURE.md](handoff/ARCHITECTURE.md).

## Notes

- Event names shown in the feed (e.g. "UFC 329: …") come from Polymarket's
  market data and are factual references to third-party events; this project
  is not affiliated with any MMA promotion or with Polymarket.
- AI output explains market movements; it is not betting advice.

## License

[MIT](LICENSE)
