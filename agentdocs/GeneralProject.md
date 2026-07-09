# AgentPredict — Component Docs Index

Per-component reference for people (or agents) modifying the code. Current as
of 2026-07-09. For narrative orientation read `humandocs/ProjectOverview.md`;
for ops read `handoff/`.

| Doc | Component |
|---|---|
| [DiagramOfTheProject.md](DiagramOfTheProject.md) | Data-flow diagram |
| [AgentAgents.md](AgentAgents.md) | `agents/` — Polymarket + MMA pollers |
| [AgentEngine.md](AgentEngine.md) | `engine/` — C++ validation + ring buffer |
| [AgentRag.md](AgentRag.md) | `rag/` — trigger policy, Gemini, Pinecone, verifier |
| [Dashboard.md](Dashboard.md) | `dashboard/` — React SPA + gateway WebSocket |
| [PolymarketAPI.md](PolymarketAPI.md) | External API notes: Gamma + CLOB |
| [BalldontlieMMAAPI.md](BalldontlieMMAAPI.md) | External API notes: BallDontLie MMA |
| [RequirementsAndRestrictions.md](RequirementsAndRestrictions.md) | Invariants you must not break |

Ground rules for any change:
- `proto/events.proto` is the single contract; changes ripple to checked-in
  Python stubs, the engine's build-time C++ stubs, and the TS mirror types.
- Every service has an offline mock so `make demo` works with zero keys —
  keep mocks shaped exactly like the real clients.
- All suites green before commit: C++ (GTest), Python (pytest), dashboard
  (vitest + tsc). Commands in `handoff/RUNBOOK.md`.
