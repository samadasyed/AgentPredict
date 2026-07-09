# Component: `rag/` — AI analysis pipeline

Subscribes to the engine's event stream, decides which odds moves deserve an
explanation, generates one grounded in retrieved evidence, verifies it, and
serves verified `RagPrediction`s to the gateway over gRPC (`RagStream`).

## Trigger policy (`orchestrator.py`) — the cost/quality core

- **Cumulative drift**: a market triggers when its probability has moved
  ≥ `_MEANINGFUL_DELTA_THRESHOLD` (`RAG_DRIFT_THRESHOLD`, default 0.01)
  since the *last explanation* (ref
  seeds at first sight as the pre-move price). One sharp tick or hours of
  slow drift both qualify; flat re-baselines never do. The trigger event's
  `delta` is rewritten to the cumulative move so the prompt describes the
  real change.
- **Fight stats**: any non-sentinel stat is a candidate; `FIGHT_UPCOMING` /
  `FIGHT_DISCOVERED` never trigger (they re-emit forever).
- **Cooldown**: ≥ `RAG_MARKET_COOLDOWN_S` (90 s) between cycles per market /
  per fighter. **Single-flight**: one cycle at a time, run in a worker thread
  (`asyncio.to_thread`) so the async stream consumer keeps draining.
- **Write budget**: Pinecone upserts capped at `RAG_MAX_UPSERTS_PER_HOUR`
  (500) — the index has no TTL.

## Generation (`inference.py`)

Gemini (`gemini-2.5-flash`) with a system prompt that covers pre-event line
moves AND live fights, forbids invented causes ("say it looks like normal
repricing"), and demands a trailing `CONFIDENCE: <0..1>` line. Response
handling survives safety blocks (no bare `response.text`) and normalizes
percent-style confidences ("85" → 0.85). `describe_trigger()` builds the
human-readable trigger line (also used as the retrieval query).

## Retrieval (`retriever.py`)

`gemini-embedding-001` at 768 dims (Matryoshka-truncated); documents embed
with `task_type=retrieval_document`, queries with `retrieval_query`.
Namespaces `market_events` / `fight_events`; index auto-created.

## Verification (`verifier.py`)

Rejects unless confidence ≥ 0.5 AND the text contains a meaningful name
token from the trigger (per-token matching so "Jones" counts for "Jon
Jones"; generic tokens and the promotion name don't count). **Only passing
results are broadcast** — failures are logged, users never see filler.

## Mocks & tests

`mock_components.py` provides keyless retriever/inference for `MOCK_MODE=1`.
Tests in `rag/tests/unit/` pin the drift trigger, cooldowns, budget, safety
handling, confidence parsing, and verifier behavior.
