# Data-Flow Diagram

```
Polymarket Gamma/CLOB        BallDontLie MMA
      │  HTTPS polling             │  HTTPS polling
      ▼                            ▼
agents/polymarket            agents/mma
      │   CanonicalEvent{MarketEvent}   │ CanonicalEvent{FightStatEvent}
      └──────────────┬─────────────────┘
                     ▼  gRPC EventIngestion (:50051)
                engine (C++)
        Normalizer → EventStore (ring buffer)
                     │  gRPC EventStream.Subscribe
        ┌────────────┴──────────────┐
        ▼                           ▼
   rag/orchestrator            gateway (FastAPI)
   trigger → retrieve →             │
   Gemini → verify                  │
        │ gRPC RagStream (:50052)   │
        └──────────► gateway ───────┤
                                    ▼  WS /ws  {"type":"event"|"prediction"}
                          dashboard (React) ── nginx (prod, :80)
                                    ▲
                     Cloudflare Tunnel / reverse proxy (prod)
```

Two independent streams reach the browser over one WebSocket:
- **Stream 1 (factual)**: every validated market/fight event.
- **Stream 2 (analysis)**: verified `RagPrediction`s.

Phases (`upcoming|live|final`), odds history snapshots, and fight metadata all
ride on Stream 1 events — the dashboard derives its entire UI from the stream
(no REST endpoints besides `/health`).
