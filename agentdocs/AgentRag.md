# Agent Doc — RAG Orchestrator
**Owner:** FWS
**Component:** `rag/`
**Language:** Python 3.11+
**Role:** Subscribe to the engine's event stream, run the agentic RAG loop on meaningful events, and serve `RagPrediction` results to the gateway over gRPC.

---

## What's Already Done

| File | Status |
|---|---|
| `orchestrator.py` | Complete — agentic loop, engine subscription, `RagStreamServiceImpl` gRPC server |
| `context_builder.py` | Complete — sliding window deque, text serialization |
| `retriever.py` | Complete — Pinecone upsert + query, Gemini embedding |
| `inference.py` | Complete — Gemini Flash prompt, confidence parsing |
| `verifier.py` | Complete — confidence threshold, hallucination check |
| `tests/unit/test_orchestrator.py` | Complete — 5 async tests |
| `tests/unit/test_retriever.py` | Complete — 5 tests |
| `tests/unit/test_inference.py` | Complete — 7 tests |
| `tests/api/test_pinecone_api.py` | Complete — 3 live API tests |
| `tests/api/test_gemini_api.py` | Complete — 3 live API tests |
| `agents/generated/` | **Must be generated from proto before running** |
| `rag/Dockerfile` | **Missing — you need to create this** |

---

## First Thing: Generate Proto Stubs

`rag/` imports from `agents.generated` — run from the **project root**:

```bash
pip install grpcio-tools
python -m grpc_tools.protoc \
  -I proto \
  --python_out=agents/generated \
  --grpc_python_out=agents/generated \
  proto/events.proto
touch agents/generated/__init__.py
```

---

## How the Agentic Loop Works

Every canonical event from the engine passes through this pipeline in `orchestrator.py`:

```
CanonicalEvent arrives
        │
        ▼
context_builder.add(event)          ← always — builds the sliding window
        │
        ▼
_is_meaningful(event)?              ← market delta >= 0.02, or any fight event
    NO  │  YES
        │   │
        │   ▼
        │  context_builder.build_context()   ← compact text of last 20 events per source
        │   │
        │   ▼
        │  retriever.retrieve(query)          ← Pinecone similarity search
        │   │
        │   ▼
        │  retriever.upsert(event)            ← grow the knowledge base
        │   │
        │   ▼
        │  inference.explain(event, ctx, evidence)   ← Gemini Flash
        │   │
        │   ▼
        │  verifier.verify(explanation, confidence, event)
        │   │
        │   ▼
        │  rag_service.broadcast(RagPrediction)      ← to gateway subscribers
        │
       skip
```

---

## Your TODOs

### 1. Create `rag/Dockerfile`

Needs to:
- Base: `python:3.11-slim`
- Install `requirements.txt`
- Copy the whole project (rag imports from `agents.generated`)
- Run proto codegen as part of build
- `CMD ["python", "-m", "rag.orchestrator"]`

### 2. Tune `_MEANINGFUL_DELTA_THRESHOLD` (`orchestrator.py`)

Currently set to `0.02` (2% probability shift). After testing with real Polymarket data, adjust this to find the right signal-to-noise ratio:
```python
_MEANINGFUL_DELTA_THRESHOLD = 0.02
```
Too low → inference runs constantly and burns Gemini API quota. Too high → misses genuine market moves.

### 3. Improve the retrieval query (`orchestrator.py`)

Currently uses just the outcome/stat_type string as the query:
```python
query = (
    event.market_event.outcome if event.HasField("market_event")
    else event.fight_event.stat_type
)
evidence = self._retriever.retrieve(query_text=query)
```
A richer query (e.g. including the market_id, probability, and delta) would return more relevant evidence. Experiment with what gives the best Pinecone similarity results.

### 4. `RagStreamServiceImpl` thread safety (`orchestrator.py`)

The `_subscribers` list is modified from both the gRPC thread (when a gateway connects) and the event loop thread (on broadcast). The current `asyncio.Lock` is not safe to use from the gRPC thread pool. Options:
- Use a `threading.Lock` instead
- Or move subscriber management into the asyncio event loop using `asyncio.Queue` per subscriber (already the pattern used in `SubscribePredictions`)

### 5. Prompt tuning (`inference.py`)

The system prompt and user prompt template are in `inference.py`. Iterate on these to improve explanation quality:
```python
_SYSTEM_PROMPT = """
You are a live UFC / Polymarket trading analyst...
"""
```
Key things to try:
- Add few-shot examples of good explanations
- Ask the model to identify whether the move is driven by a fight event vs market sentiment
- Experiment with asking for a confidence rationale separately from the explanation

### 6. Pinecone index region (`retriever.py`)

Currently hardcoded to `aws / us-east-1`:
```python
spec=ServerlessSpec(cloud="aws", region="us-east-1")
```
Change this to match whatever region your Pinecone account is in.

---

## Interfaces You Must Not Break

### `RagStream` gRPC service (defined in `proto/events.proto`)

```protobuf
service RagStream {
  rpc SubscribePredictions(RagSubscribeRequest) returns (stream RagPrediction);
}
```

The gateway subscribes here. `SubscribePredictions` must:
- Stream indefinitely until the client cancels
- Filter predictions where `confidence < request.min_confidence`
- Never raise — log errors and continue

### `RagPrediction` fields the gateway expects

```protobuf
message RagPrediction {
  string explanation      = 1;   // non-empty string
  repeated EvidenceItem evidence = 2;
  double confidence       = 3;   // [0, 1]
  int64  timestamp        = 4;   // unix millis
  string trigger_event_id = 5;   // must match a real event_id from engine
}
```

All fields must be set. The dashboard renders all of them.

### Verifier output
The verifier replaces low-confidence explanations with a neutral message — it never suppresses the prediction entirely. A `RagPrediction` is always emitted for every meaningful event, even if `passed=False`. This ensures the dashboard always shows something for a meaningful market move.

---

## Dependencies

| Dependency | Notes |
|---|---|
| `agents/generated/` | Proto stubs — must be generated first |
| `ENGINE_GRPC_ADDRESS` | Engine gRPC address (default `localhost:50051`) |
| `RAG_GRPC_ADDRESS` | Address this service listens on (default `0.0.0.0:50052`) |
| `GOOGLE_API_KEY` | Required — used for both Gemini Flash and text-embedding-004 |
| `PINECONE_API_KEY` | Required — Pinecone vector store |
| `PINECONE_INDEX_NAME` | Default: `agentpredict` |

---

## Run

```bash
# From project root
python -m rag.orchestrator
```

The orchestrator starts two things concurrently:
1. A gRPC server on `RAG_GRPC_ADDRESS` (`:50052`) for the gateway to subscribe to
2. An async loop that subscribes to the engine's EventStream on `ENGINE_GRPC_ADDRESS`

The engine must be running before the orchestrator starts — it will retry the engine connection every 5 seconds on failure.

---

## Tests

**Unit tests (all external deps mocked — no API keys needed):**
```bash
pytest rag/tests/unit/ -v
```

**Live API tests (require `GOOGLE_API_KEY` and `PINECONE_API_KEY`):**
```bash
pytest -m api rag/tests/api/ -v
```

The live tests:
- `test_pinecone_api.py` — upserts a test event and retrieves it back (2s sleep to let Pinecone index it)
- `test_gemini_api.py` — makes a real inference call and checks the response shape

When writing new tests, mock `Pinecone`, `genai`, and proto stubs — never make real API calls in unit tests. See existing tests for the mock pattern.

---

## Key Design Decisions to Know

- **Context builder runs on every event, not just meaningful ones.** This ensures the sliding window always reflects the full picture, even for sub-threshold market noise.
- **Every meaningful event is upserted to Pinecone before retrieval.** This means the knowledge base grows over the session. Historical pattern retrieval improves as the fight progresses.
- **The verifier does not drop predictions — it downgrades them.** Even a `passed=False` result emits a prediction with a neutral explanation. The confidence value is always real so the dashboard's confidence bar reflects true model certainty.
- **`_is_meaningful` uses delta >= 0.02 for market events, but all fight events pass.** Fight events are rare on the free tier (`FIGHT_DISCOVERED` only) so there's no need to gate them.
