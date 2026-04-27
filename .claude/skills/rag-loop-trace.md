---
name: rag-loop-trace
description: Trace a single CanonicalEvent end-to-end through AgentPredict (agent emit → engine normalize → engine ring → rag handle → context/retrieve/infer/verify → broadcast → gateway → WebSocket → dashboard). Use when debugging RAG predictions, missing events, hallucinated explanations, or low-confidence outputs.
---

# RAG event-loop trace

When a prediction looks wrong / missing / low-confidence, walk the pipeline in order. Each stage has a specific failure mode.

## Hop-by-hop checklist

### 1. Agent emit (`agents/{polymarket,mma}/agent.py`)

- Polymarket emits when `abs(delta) >= POLYMARKET_DELTA_THRESHOLD` (default 0.01)
- MMA free-tier emits **only** `FIGHT_DISCOVERED` (one per fight_id ever)
- Failure mode: agent prints "no active markets" / "no live events" — no event leaves the process
- Verify: `DEBUG_DUMP=1 python -m agents.polymarket.agent` → check `/tmp/polymarket_debug/`

### 2. gRPC ingest (`agents/shared/event_emitter.py`)

- Single `grpc.insecure_channel` per agent process; `IngestEvent` returns an `IngestAck`
- `accepted=False` is **not** a gRPC error — engine's normalizer rejected the payload
- Verify: agent logs `[emitter] engine rejected event ...: <reason>`

### 3. Engine normalize (`engine/src/normalizer.cpp`)

Validation rules (any failure → `accepted=False`):
- `source != SOURCE_UNKNOWN`
- payload (market_event or fight_event) is set
- `MarketEvent.probability ∈ [0, 1]`
- `MarketEvent.market_id` non-empty
- `FightStatEvent.fight_id` and `fighter_name` non-empty
- source timestamp within ±60s of server time

On success, stamps `event_id` (UUID v4) and `ingested_at` (unix millis).

### 4. Engine ring buffer (`engine/src/event_store.cpp`)

- Fixed capacity (default 4096, power of 2). Slow readers > capacity behind silently jump to oldest available.
- `EventStream.Subscribe` (gRPC :50051) loops `GetSince(cursor)` + `WaitForNew(cursor, timeout_ms)`.

### 5. RAG handle (`rag/orchestrator.py::Orchestrator._handle_event`)

```
context_builder.add(event)            # always — even sub-threshold
if not _is_meaningful(event): return  # market: |delta| >= 0.02; fight: always
context_text = context_builder.build_context()
query        = event.market_event.outcome  OR  event.fight_event.stat_type
evidence     = retriever.retrieve(query)         # Pinecone, top_k=5, both namespaces
retriever.upsert(event)                          # grow KB
result       = inference.explain(event, context_text, evidence)  # Gemini Flash
verified     = verifier.verify(result.explanation, result.confidence, event)
rag_service.broadcast(prediction)
```

- Sub-threshold market events (delta < 0.02) update context but emit no prediction. **Expected behavior — not a bug.**
- Inference failures are caught and logged; the cycle does not crash.

### 6. Verifier (`rag/verifier.py`)

Two checks; if either fails, explanation → neutral fallback (but prediction still emitted with `passed=False`):
- `confidence >= 0.5`
- explanation text mentions `market_id`/`outcome` (markets) or `fight_id`/`fighter_name` (fights)

If you see "Insufficient confidence to provide a reliable explanation" on the dashboard, the verifier downgraded it. Check: was confidence < 0.5, or did Gemini ignore the trigger event?

### 7. Broadcast (`rag/orchestrator.py::RagStreamServiceImpl`)

- Each gateway subscriber gets a `Queue(maxsize=100)`. Full queue drops silently.
- **Known thread-safety bug:** `_subscribers` list is mutated from gRPC thread pool but `_lock` is `asyncio.Lock`. Use `threading.Lock` or per-sub `asyncio.Queue`. Listed in agentdocs/AgentRag.md TODOs.
- **Known typo:** `while not context.is_active() is False` — double-negative on line ~110. Should be `while context.is_active()`.

### 8. Gateway (`gateway/rag_subscriber.py` → `broadcaster.py`)

- Subscribes to `RagStream` (gRPC :50052), converts proto → dict via `MessageToDict(preserving_proto_field_name=True)`, fans out to all WS clients.
- On any gRPC error: 5s sleep, reconnect.
- WS envelope: `{"type": "prediction", "data": {...}}`.

### 9. Dashboard (`dashboard/src/hooks/useEventStream.ts`)

- Routes `type: "prediction"` → `predictions[]` (max 50, newest first).
- Reconnects after 3s on close/error. `StreamWarning` banner shows on disconnect.

## Quick triage table

| Symptom | First place to look |
|---|---|
| No prediction for a clear price spike | RAG `_is_meaningful` threshold (0.02) — too high? Or context overflow → check Pinecone latency |
| Always neutral fallback | Verifier — likely `confidence < 0.5` or hallucinated (no market_id mention) |
| Predictions stop after a while | Gateway subscriber queue full (100) → dashboard slow consumer; or RAG thread-safety bug stalling broadcasts |
| Engine accepts=false | Normalizer — check probability range, timestamp skew, empty IDs |
| RAG can't connect | `ENGINE_GRPC_ADDRESS` env; engine retry loop is 5s in orchestrator |
