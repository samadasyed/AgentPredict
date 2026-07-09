# Repo Tour

*Where things live and what you'd touch to change them. Paths are repo-relative.*

## The contract everything shares

`proto/events.proto` — one file defines every message that crosses a service
boundary. Change it and you must regenerate the checked-in Python stubs
(`agents/generated/`, recipe in `handoff/RUNBOOK.md`), let the engine image
rebuild its C++ stubs, and mirror the change in
`dashboard/src/types/events.ts`.

## Services

- **`agents/polymarket/`** — market discovery (`client.py`: tagged-events API,
  moneyline selection, price history), polling/emit policy (`agent.py`:
  delta threshold, periodic re-baselines), API shapes (`models.py`),
  offline stand-in (`mock_client.py`).
- **`agents/mma/`** — same shape for BallDontLie: card discovery, live-event
  detection, stat polling behind the GOAT-tier flag.
- **`engine/`** — C++20. `src/normalizer.*` (validation rules),
  `src/event_store.*` (lock-protected ring buffer with cursor reads),
  `src/grpc_server.*` (Ingest + Subscribe services). GTest suites in `tests/`.
- **`rag/`** — `orchestrator.py` (trigger policy, cooldowns, budgets, the
  agentic loop), `inference.py` (Gemini prompt + response handling),
  `retriever.py` (Pinecone + embeddings), `verifier.py` (grounding gate),
  `context_builder.py` (sliding window), `mock_components.py` (offline).
- **`gateway/`** — `server.py` (FastAPI app, `/health`, `/ws`, origin checks),
  `broadcaster.py` (fan-out + replay buffers), `engine_subscriber.py` /
  `rag_subscriber.py` (gRPC consumers with keepalive + health state),
  `proto_utils.py` (the one proto→JSON call site).
- **`dashboard/`** — React SPA. View-model logic is deliberately concentrated
  in `src/lib/marketSeries.ts` (series building, phases, fusion helpers) and
  `src/lib/fights.ts` (schedule+market merge, card ordering); components under
  `src/components/` are mostly presentation. `Dockerfile` is the production
  nginx image; `Dockerfile.dev` the Vite dev server.

## Everything else

- `docker-compose.yml` / `.mock.yml` / `.prod.yml` — dev, demo, production stacks.
- `scripts/run-stack.sh {mock|real|prod}` — no-compose launcher (rootless podman).
- `agentdocs/` — per-component reference (current).
- `handoff/` — architecture constraints, runbook, deployment guide, build audit.
- `.env.example` — the environment template (placeholders only; copy to `.env`).
