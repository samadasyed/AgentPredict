# AgentPredict

Real-time UFC prediction dashboard. Correlates live [Polymarket](https://polymarket.com) odds changes with live UFC fight statistics, then uses agentic RAG to generate plain-text explanations of why the odds moved.

**Target audience:** Polymarket retail traders watching live UFC events.

---

## Table of Contents

1. [How It Works](#how-it-works)
2. [Architecture](#architecture)
3. [Data Flow](#data-flow)
4. [Directory Structure](#directory-structure)
5. [Component Reference](#component-reference)
   - [proto/](#proto)
   - [engine/](#engine)
   - [agents/](#agents)
   - [rag/](#rag)
   - [gateway/](#gateway)
   - [dashboard/](#dashboard)
6. [gRPC Services](#grpc-services)
7. [WebSocket Message Format](#websocket-message-format)
8. [Environment Variables](#environment-variables)
9. [Running Locally](#running-locally)
10. [Testing](#testing)
11. [Team Ownership](#team-ownership)
12. [Known Limitations / TODOs](#known-limitations--todos)

---

## How It Works

1. **Polymarket agent** polls active UFC markets every 5 seconds. When a token's implied probability shifts by ≥ 1%, it emits a `MarketEvent` to the C++ engine.
2. **MMA agent** polls BallDontLie for live UFC events. It emits a `FIGHT_DISCOVERED` event when a new fight appears. Full per-round stats require the GOAT tier (currently stubbed).
3. **C++ engine** receives events from both agents, validates them (probability range, clock skew, non-empty IDs), stamps a UUID + ingestion timestamp, and stores them in a ring buffer.
4. **Gateway** subscribes to the engine's event stream and fans all events out to connected browser clients as JSON over WebSocket — this is **Stream 1** (factual only, no predictions).
5. **RAG orchestrator** also subscribes to the engine. For each "meaningful" event (delta ≥ 2%), it runs the full agentic reasoning loop and emits a `RagPrediction`.
6. **Gateway** subscribes to the RAG orchestrator and fans predictions to browsers — this is **Stream 2**.
7. **Dashboard** shows both streams side-by-side: raw events on the left, AI analysis with evidence on the right.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        External Sources                         │
│   Polymarket CLOB API              BallDontLie MMA API          │
└──────────────┬──────────────────────────────┬───────────────────┘
               │                              │
               ▼                              ▼
   ┌───────────────────┐          ┌───────────────────┐
   │  polymarket-agent │          │     mma-agent     │
   │  (Python/aiohttp) │          │  (Python/aiohttp) │
   └─────────┬─────────┘          └─────────┬─────────┘
             │  gRPC IngestEvent             │  gRPC IngestEvent
             └──────────────┬───────────────┘
                            ▼
              ┌─────────────────────────┐
              │      C++ Engine         │
              │  ┌───────────────────┐  │
              │  │    Normalizer     │  │  validates + stamps UUID
              │  └────────┬──────────┘  │
              │           ▼             │
              │  ┌───────────────────┐  │
              │  │   Event Store     │  │  ring buffer, cursors
              │  └────────┬──────────┘  │
              │           │  gRPC       │
              │    EventStream.Subscribe│
              └───────────┬─────────────┘
                          │
             ┌────────────┴─────────────┐
             ▼                          ▼
   ┌──────────────────┐      ┌───────────────────────┐
   │     Gateway      │      │   RAG Orchestrator    │
   │  (FastAPI + WS)  │      │  ┌─────────────────┐  │
   │                  │      │  │ ContextBuilder  │  │
   │  /ws  /health    │      │  ├─────────────────┤  │
   └────────┬─────────┘      │  │   Retriever     │  │  Pinecone
            │                │  │  (Pinecone)     │  │
            │   ◄────────────│  ├─────────────────┤  │
            │  gRPC          │  │   Inference     │  │  Gemini Flash
            │  RagStream     │  │  (Gemini Flash) │  │
            │                │  ├─────────────────┤  │
            │                │  │    Verifier     │  │
            │                │  └─────────────────┘  │
            │                │  gRPC RagStream server │
            │                └───────────────────────┘
            │
            ▼  WebSocket JSON
   ┌──────────────────┐
   │    Dashboard     │
   │  (React + Vite)  │
   │                  │
   │  Stream 1│Stream2│
   │  Events  │Preds  │
   └──────────────────┘
```

---

## Data Flow

### Stream 1 — Factual Events

```
Agent → gRPC IngestEvent → C++ Engine (validate + store)
      → gRPC EventStream → Gateway → WebSocket → Browser
```

- Contains only observed facts: price changed, fight discovered.
- **No predictive language.**

### Stream 2 — AI Predictions

```
C++ Engine → gRPC EventStream → RAG Orchestrator
  → ContextBuilder (sliding window)
  → Retriever (Pinecone similarity search)
  → Inference (Gemini Flash: explanation + confidence)
  → Verifier (confidence threshold + hallucination check)
  → gRPC RagStream → Gateway → WebSocket → Browser
```

- Always includes evidence (retrieved passages + similarity scores).
- Low-confidence predictions (< 0.5) are replaced with a neutral message.

---

## Directory Structure

```
/
├── proto/
│   └── events.proto              # gRPC contracts — single source of truth
│
├── engine/                       # C++ Central Engine
│   ├── CMakeLists.txt
│   ├── src/
│   │   ├── main.cpp
│   │   ├── engine.hpp / .cpp     # top-level wiring
│   │   ├── normalizer.hpp / .cpp # stateless validator
│   │   ├── event_store.hpp / .cpp# ring buffer
│   │   └── grpc_server.hpp / .cpp# gRPC service impls
│   └── tests/unit/
│       ├── test_normalizer.cpp
│       ├── test_event_store.cpp
│       └── CMakeLists.txt
│
├── agents/                       # Python API polling agents
│   ├── shared/
│   │   ├── event_emitter.py      # gRPC client to engine
│   │   └── retry.py              # backoff decorator
│   ├── polymarket/
│   │   ├── models.py             # Pydantic shapes
│   │   ├── client.py             # async HTTP + caching
│   │   └── agent.py              # poll loop
│   ├── mma/
│   │   ├── models.py
│   │   ├── client.py             # GOAT-tier STUBBED
│   │   └── agent.py
│   └── tests/
│       ├── unit/
│       └── api/
│
├── rag/                          # RAG Orchestrator
│   ├── orchestrator.py           # agentic loop + RagStream server
│   ├── context_builder.py        # sliding window
│   ├── retriever.py              # Pinecone + embeddings
│   ├── inference.py              # Gemini Flash
│   ├── verifier.py               # confidence + hallucination check
│   └── tests/
│       ├── unit/
│       └── api/
│
├── gateway/                      # WebSocket bridge
│   ├── server.py                 # FastAPI app
│   ├── broadcaster.py            # fan-out to browsers
│   ├── engine_subscriber.py      # gRPC → broadcaster
│   ├── rag_subscriber.py         # gRPC → broadcaster
│   └── tests/unit/
│
├── dashboard/                    # React frontend
│   ├── src/
│   │   ├── hooks/useEventStream.ts
│   │   ├── types/events.ts
│   │   ├── types/rag.ts
│   │   └── components/
│   │       ├── layout/
│   │       ├── events/
│   │       ├── predictions/
│   │       └── shared/
│   └── src/tests/
│
├── docker-compose.yml
├── .env.example
├── requirements.txt
└── pytest.ini
```

---

## Component Reference

### `proto/`

**`events.proto`** is the single source of truth. Every other component either generates stubs from it (C++ via `protoc`, Python via `grpc_tools.protoc`) or mirrors its shapes (TypeScript types in the dashboard).

Key message types:

| Message | Fields |
|---|---|
| `MarketEvent` | market_id, outcome, probability [0–1], delta, timestamp |
| `FightStatEvent` | fight_id, fighter_name, stat_type, value, round, timestamp |
| `CanonicalEvent` | event_id (UUID), source enum, ingested_at, oneof {market_event, fight_event} |
| `RagPrediction` | explanation, evidence[], confidence, timestamp, trigger_event_id |
| `EvidenceItem` | text, source_ref, score |

**Generating stubs:**

```bash
# C++ (run inside engine/build directory)
cmake --build .   # CMakeLists.txt handles codegen via add_custom_command

# Python (run from project root)
python -m grpc_tools.protoc \
  -I proto \
  --python_out=agents/generated \
  --grpc_python_out=agents/generated \
  proto/events.proto
```

The generated Python stubs go in `agents/generated/` — that directory is referenced by `agents/shared/event_emitter.py`, `rag/`, and `gateway/`.

---

### `engine/`

**Language:** C++20
**Build system:** CMake 3.22+
**Dependencies:** gRPC, Protobuf, nlohmann_json, GTest, Threads

#### Normalizer (`src/normalizer.hpp`)

Stateless — thread-safe without locks. Called on every incoming event before it touches the store.

Validation rules:
- `source` must not be `SOURCE_UNKNOWN`
- Payload must be set (market_event or fight_event)
- `MarketEvent.probability` must be in [0.0, 1.0]
- `MarketEvent.market_id` must be non-empty
- `FightStatEvent.fight_id` and `fighter_name` must be non-empty
- Source timestamp must be within ±60 seconds of server time

On success, stamps `event_id` (UUID v4) and `ingested_at` (unix millis).

#### EventStore (`src/event_store.hpp`)

Fixed-capacity ring buffer. Capacity must be a power of 2 (default: 4096).

- `Append()` — exclusive write lock, wakes all waiting subscribers
- `GetSince(cursor)` — shared read lock, returns events since that cursor
- `WaitForNew(cursor, timeout_ms)` — blocks on `condition_variable_any`; avoids busy-wait in the gRPC Subscribe loop
- Readers that fall > capacity events behind silently skip to the oldest available event

#### GrpcServer (`src/grpc_server.hpp`)

Two service implementations sharing the same `EventStore` and `Normalizer` via `shared_ptr`:

- **`EventIngestionServiceImpl`** — agents call `IngestEvent` / `IngestStream`; normalizes and appends
- **`EventStreamServiceImpl`** — gateway calls `Subscribe`; loops `GetSince` + `WaitForNew`, streams events back

**Build:**
```bash
cd engine
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build
./build/engine
```

**Run under ThreadSanitizer:**
```bash
cmake -B build -DCMAKE_CXX_FLAGS="-fsanitize=thread -g"
cmake --build build
cd build && ctest -V
```

---

### `agents/`

**Language:** Python 3.11+
**Key libs:** aiohttp, grpcio, pydantic

#### `shared/retry.py`

Decorator for async functions. Features:
- Exponential backoff: `min(base_delay * 2^(attempt-1), max_delay)`
- Jitter: adds up to 30% random noise to avoid thundering herd
- `retryable` param: only listed exception types trigger a retry — all others propagate immediately

```python
@retry(max_attempts=5, base_delay=1.0, retryable=(aiohttp.ClientError,))
async def my_api_call():
    ...
```

#### `shared/event_emitter.py`

Single gRPC channel reused for the lifetime of the agent process. gRPC channels handle reconnection internally. Provides `emit(event)` and `emit_stream(events)`.

#### `polymarket/`

- **`client.py`** — caches market IDs for 5 minutes; handles 429 `Retry-After` headers; optional `DEBUG_DUMP=1` to save raw JSON to `/tmp/polymarket_debug/`
- **`agent.py`** — polls every `POLYMARKET_POLL_INTERVAL_S` seconds (default 5); only emits when `abs(delta) >= POLYMARKET_DELTA_THRESHOLD` (default 0.01)

#### `mma/`

- **`client.py`** — `get_live_events()` is active on the free tier. `get_fight_stats()` and `get_round_stats()` always raise:
  ```
  NotImplementedError("BallDontLie GOAT tier required")
  ```
  Do not remove these stubs — they are intentional placeholders.
- **`agent.py`** — tracks seen `fight_id`s; emits a `FIGHT_DISCOVERED` synthetic event the first time each fight appears. Logs a warning at startup about GOAT tier being disabled.

---

### `rag/`

**Language:** Python 3.11+
**Key libs:** google-generativeai, pinecone-client, grpcio
**Owner:** FWS

#### `context_builder.py`

Maintains a `deque(maxlen=20)` per source (Polymarket + MMA). Every canonical event is added here regardless of whether it triggers inference. `build_context()` serializes both windows into a compact block injected into the LLM prompt.

#### `retriever.py`

Pinecone index with two namespaces:
- `market_events` — Polymarket canonical events
- `fight_events` — MMA canonical events

Every meaningful event is upserted (builds the knowledge base over time). `retrieve(query_text)` embeds the query with Gemini `text-embedding-004` (768-dim), queries both namespaces, merges results by score.

#### `inference.py`

`gemini-1.5-flash` model. The prompt structure:
1. System: analyst role + rules (2–3 sentences, grounded only, no speculation)
2. User: triggering event description + recent context + retrieved evidence
3. Model must end its response with `CONFIDENCE: <float>`

The `_parse_response()` method strips the confidence line from the explanation and clamps the value to [0, 1].

#### `verifier.py`

Two checks before a prediction is broadcast:
1. `confidence >= 0.5` — otherwise emits a neutral fallback message
2. The explanation text must contain the `market_id` or `fighter_name` from the trigger event — catches responses that ignore the actual event data

#### `orchestrator.py`

Agentic loop:

```
for each incoming CanonicalEvent:
  context_builder.add(event)           # always
  if not _is_meaningful(event):        # delta < 0.02 → skip inference
      continue
  context  = context_builder.build_context()
  evidence = retriever.retrieve(query)
  retriever.upsert(event)              # grow the store
  result   = inference.explain(event, context, evidence)
  verified = verifier.verify(result.explanation, result.confidence, event)
  rag_service.broadcast(RagPrediction)
```

Also implements `RagStreamServiceImpl` (gRPC server on `:50052`) so the gateway can subscribe.

---

### `gateway/`

**Language:** Python 3.11+
**Key libs:** FastAPI, uvicorn, grpcio
**Owner:** Samad

#### `broadcaster.py`

`asyncio.Lock`-protected `set[WebSocket]`. Fan-out: iterates all clients, sends JSON, silently removes any that raise on send.

> **TODO:** buffer last 50 events for late-joining clients (reconnect replay).

#### `engine_subscriber.py` / `rag_subscriber.py`

Both follow the same pattern:
1. Open a gRPC channel to the upstream service
2. Call `Subscribe` / `SubscribePredictions` — get an async generator
3. Convert each proto message to a dict via `MessageToDict(preserving_proto_field_name=True)`
4. Call `broadcaster.broadcast({"type": "event"|"prediction", "data": {...}})`
5. On any gRPC error, wait 5 seconds and reconnect

#### `server.py`

FastAPI lifespan starts both subscriber tasks on startup and cancels them on shutdown.

```
GET  /health  → {"status": "ok", "ws_clients": N}
WS   /ws      → browser WebSocket endpoint
```

**Run:**
```bash
uvicorn gateway.server:app --host 0.0.0.0 --port 8000
```

---

### `dashboard/`

**Stack:** React 18, Vite 5, TypeScript 5, Tailwind CSS 3
**Owner:** Zaid

#### `hooks/useEventStream.ts`

Manages the full WebSocket lifecycle:
- Connects to `VITE_GATEWAY_WS_URL` (default `ws://localhost:8000/ws`)
- Routes `type: "event"` → `events[]` state (max 200, newest first)
- Routes `type: "prediction"` → `predictions[]` state (max 50, newest first)
- Reconnects after 3 seconds on any close/error
- Sets `error` string on malformed JSON or unknown message type

#### Layout

```
┌─────────── Header ───────────────┐
│ AgentPredict    ● connected      │
├──────────────────────────────────┤
│  [StreamWarning if disconnected] │
├──────────────┬───────────────────┤
│  EventFeed   │  PredictionFeed   │
│  (Stream 1)  │  (Stream 2)       │
│              │                   │
│  EventCard   │  PredictionCard   │
│  EventCard   │    explanation    │
│  ...         │    ████░░ 72%     │
│              │    Evidence:      │
│              │    [92%] text...  │
│              │                   │
└──────────────┴───────────────────┘
```

#### Color coding

| Element | Color |
|---|---|
| Polymarket source badge | Blue (`#3B82F6`) |
| MMA source badge | Orange (`#F97316`) |
| Positive delta | Green |
| Negative delta | Red |
| Confidence > 70% bar | Green |
| Confidence 50–70% bar | Yellow |
| Stream warning banner | Amber |

**Run:**
```bash
cd dashboard
npm install
npm run dev        # dev server on :5173
npm test           # Vitest
npm run build      # production build
```

---

## gRPC Services

| Service | Server | Client(s) | Port | Purpose |
|---|---|---|---|---|
| `EventIngestion` | C++ engine | polymarket-agent, mma-agent | 50051 | Agents push events in |
| `EventStream` | C++ engine | gateway, rag-orchestrator | 50051 | Subscribe to live event stream |
| `RagStream` | Python rag | gateway | 50052 | Subscribe to prediction stream |

All communication is insecure (`grpc.insecure_channel`) in development. Add TLS + auth interceptor before any production deployment.

---

## WebSocket Message Format

Every message from the gateway is a JSON envelope:

```json
// Stream 1 — factual event
{
  "type": "event",
  "data": {
    "event_id": "550e8400-e29b-41d4-a716-446655440000",
    "source": "SOURCE_POLYMARKET",
    "ingested_at": 1710000000000,
    "market_event": {
      "market_id": "0xabc...",
      "outcome": "Fighter A wins",
      "probability": 0.72,
      "delta": 0.08,
      "timestamp": 1710000000000
    }
  }
}

// Stream 2 — RAG prediction
{
  "type": "prediction",
  "data": {
    "explanation": "Fighter A's probability jumped after landing a clean combination in round 2, significantly shifting bettors' assessment of the fight.",
    "evidence": [
      { "text": "Fighter A landed 3 consecutive jabs.", "source_ref": "market_events/abc", "score": 0.92 }
    ],
    "confidence": 0.81,
    "timestamp": 1710000000100,
    "trigger_event_id": "550e8400-e29b-41d4-a716-446655440000"
  }
}
```

---

## Environment Variables

Copy `.env.example` to `.env` and fill in values:

| Variable | Required | Description |
|---|---|---|
| `ENGINE_GRPC_ADDRESS` | Yes | e.g. `localhost:50051` |
| `RAG_GRPC_ADDRESS` | Yes | e.g. `localhost:50052` |
| `GATEWAY_WS_URL` | Dashboard | e.g. `ws://localhost:8000/ws` |
| `GOOGLE_API_KEY` | RAG | Gemini Flash + text-embedding-004 |
| `PINECONE_API_KEY` | RAG | Pinecone vector store |
| `PINECONE_INDEX_NAME` | RAG | Default: `agentpredict` |
| `BALLDONTLIE_API_KEY` | Agents | Free tier works without key; GOAT tier requires it |
| `POLYMARKET_DELTA_THRESHOLD` | No | Default: `0.01` |
| `POLYMARKET_POLL_INTERVAL_S` | No | Default: `5` |
| `MMA_POLL_INTERVAL_S` | No | Default: `30` |
| `DEBUG_DUMP` | No | Set `1` to dump raw API JSON to `/tmp/` |

---

## Running Locally

### With Docker Compose (recommended)

```bash
cp .env.example .env
# fill in GOOGLE_API_KEY, PINECONE_API_KEY, BALLDONTLIE_API_KEY

docker compose up --build
```

Then open `http://localhost:5173`.

> **Note:** Dockerfiles for each service still need to be created (marked with `# TODO` in `docker-compose.yml`).

### Without Docker

**1. Generate Python proto stubs:**
```bash
pip install grpcio-tools
python -m grpc_tools.protoc \
  -I proto \
  --python_out=agents/generated \
  --grpc_python_out=agents/generated \
  proto/events.proto
touch agents/generated/__init__.py
```

**2. Install Python deps:**
```bash
pip install -r requirements.txt
```

**3. Build and start the C++ engine:**
```bash
cd engine
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j$(nproc)
ENGINE_GRPC_ADDRESS=0.0.0.0:50051 ./build/engine
```

**4. Start Python services (each in a separate terminal):**
```bash
python -m agents.polymarket.agent
python -m agents.mma.agent
python -m rag.orchestrator
uvicorn gateway.server:app --port 8000
```

**5. Start the dashboard:**
```bash
cd dashboard
npm install
npm run dev
```

---

## Testing

### C++ (GTest)
```bash
cd engine/build
ctest -V

# With ThreadSanitizer
cmake -B build -DCMAKE_CXX_FLAGS="-fsanitize=thread -g"
cmake --build build && cd build && ctest -V
```

### Python unit tests (no external services needed)
```bash
pytest agents/tests/unit/
pytest rag/tests/unit/
pytest gateway/tests/unit/
```

### Python live API tests (require API keys + internet)
```bash
pytest -m api agents/tests/api/
pytest -m api rag/tests/api/
```

### Frontend (Vitest)
```bash
cd dashboard
npm test
```

---

## Team Ownership

| Component | Owner(s) |
|---|---|
| `proto/events.proto` | Samad |
| `engine/` | Samad |
| `agents/shared/` | Samad + Saify |
| `agents/polymarket/` | Saify |
| `agents/mma/` | Saify |
| `rag/` | FWS |
| `gateway/` | Samad |
| `dashboard/` | Zaid |
| `docker-compose.yml`, `.env.example` | Samad |

---

## Known Limitations / TODOs

- **Dockerfiles** — all 6 service Dockerfiles still need to be created (`engine/Dockerfile`, `agents/Dockerfile`, `rag/Dockerfile`, `gateway/Dockerfile`, `dashboard/Dockerfile.dev`)
- **Proto stubs** — Python stubs in `agents/generated/` must be generated before any Python service can run (see step 1 in [Running Locally](#running-locally))
- **MMA live stats** — `get_fight_stats()` and `get_round_stats()` raise `NotImplementedError` until the BallDontLie GOAT tier ($39.99/mo) is activated
- **gRPC TLS** — all channels use `insecure_channel`; add TLS + auth interceptor before any public deployment
- **Late-join replay** — `Broadcaster` does not yet buffer the last 50 events for clients that connect mid-stream (marked TODO in `broadcaster.py`)
- **EventStore cursor resume** — `SubscribeRequest.cursor` field is defined in proto but not yet parsed in `EventStreamServiceImpl::Subscribe` (marked TODO in `grpc_server.cpp`)
- **UUID library** — `Normalizer::GenerateUUID()` uses a minimal in-house implementation; replace with `libuuid` or `boost::uuid` in production
- **Polymarket context manager** — `PolymarketClient` needs `__aenter__`/`__aexit__` added to `client.py` (temporary workaround exists in the API test file)
