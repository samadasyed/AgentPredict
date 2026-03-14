# Agent Doc — Python API Agents
**Owner:** Saify (+ Samad for shared/)
**Component:** `agents/`
**Language:** Python 3.11+
**Role:** Poll Polymarket and BallDontLie MMA APIs, detect meaningful changes, and push structured events to the C++ engine over gRPC.

---

## What's Already Done

| File | Status |
|---|---|
| `shared/retry.py` | Complete — exponential backoff + jitter decorator |
| `shared/event_emitter.py` | Complete — single gRPC channel, `emit()` and `emit_stream()` |
| `polymarket/models.py` | Complete — Pydantic shapes for API responses |
| `polymarket/client.py` | Skeleton — HTTP client written, pagination + caching wired; **see TODOs** |
| `polymarket/agent.py` | Complete — poll loop, delta gate, event builder |
| `mma/models.py` | Complete — Pydantic shapes for free and GOAT tier |
| `mma/client.py` | Skeleton — `get_live_events()` written; GOAT-tier methods stubbed |
| `mma/agent.py` | Complete — discovers fights, emits `FIGHT_DISCOVERED`, logs GOAT warning |
| `tests/unit/test_polymarket_agent.py` | Complete — 5 async unit tests |
| `tests/unit/test_mma_agent.py` | Complete — 5 async unit tests |
| `tests/api/test_polymarket_api.py` | Complete — 3 live API tests |
| `tests/api/test_mma_api.py` | Complete — 3 live API tests |
| `agents/Dockerfile` | **Missing — you need to create this** |
| `agents/generated/` | **Missing — must be generated from proto** (see setup below) |

---

## First Thing: Generate Proto Stubs

The agents import from `agents.generated` — this directory does not exist until you run:

```bash
pip install grpcio-tools
python -m grpc_tools.protoc \
  -I proto \
  --python_out=agents/generated \
  --grpc_python_out=agents/generated \
  proto/events.proto
touch agents/generated/__init__.py
```

Run this from the **project root** (`/home/agentpredict/`). After this, `agents/generated/events_pb2.py` and `agents/generated/events_pb2_grpc.py` will exist and all imports will resolve.

---

## Your TODOs

### Polymarket Agent

#### 1. Verify the `/markets` endpoint path and pagination (`polymarket/client.py`)

The current implementation calls `GET /markets` with `?active=true&next_cursor=...`. Confirm this matches the live Polymarket CLOB API:
- Docs: https://docs.polymarket.com/api-reference/introduction
- The `MarketsPage` model expects `{ data: [...], next_cursor: "..." }` — verify the real response shape matches

```python
# TODO(Saify): Polymarket CLOB may batch price requests — evaluate
#              /prices-history or websocket feed for lower latency.
```

#### 2. Verify the per-market price endpoint (`polymarket/client.py`)

Currently calls `GET /markets/{market_id}` to get token prices. Check if there's a batch prices endpoint (e.g. `/prices`) that would be more efficient for many markets.

#### 3. Add async context manager to `PolymarketClient` (`polymarket/client.py`)

The live API test file has a workaround patch. Add proper `__aenter__`/`__aexit__` to the class:
```python
async def __aenter__(self):
    return self

async def __aexit__(self, *_):
    await self.close()
```

#### 4. Auto-stop polling completed fights (`mma/agent.py`)

```python
# TODO(Saify): when GOAT tier is active, call client.get_fight_stats()
#              for each in-progress fight and emit FightStatEvents.
```
Currently the agent only emits `FIGHT_DISCOVERED` once. When GOAT tier is enabled:
- Poll `get_fight_stats(fight_id)` for every `in_progress` fight each cycle
- Build a `FightStatEvent` for each meaningful stat change
- Stop polling when `fight.status == "completed"` and remove from tracking set

#### 5. Create `agents/Dockerfile`

Needs to:
- Base: `python:3.11-slim`
- Copy `requirements.txt` and install deps
- Copy the whole project (since agents import from `agents.generated`, `agents/`, etc.)
- Run proto codegen as part of the build step
- No default `CMD` — docker-compose sets it per service

---

## GOAT Tier Stubs — Do Not Remove

`mma/client.py` has two methods that always raise:

```python
async def get_fight_stats(self, fight_id: int) -> list[FightStat]:
    raise NotImplementedError("BallDontLie GOAT tier required ...")

async def get_round_stats(self, fight_id: int, round_num: int) -> list[RoundStat]:
    raise NotImplementedError("BallDontLie GOAT tier required ...")
```

**Do not remove or silence these.** They are intentional placeholders. When the GOAT tier is activated:
1. Remove the `raise NotImplementedError` line
2. Implement the actual API call using the BallDontLie docs: https://mma.balldontlie.io/?python#get-fight-statistics
3. Update `mma/agent.py` to call these methods in `_poll_once()`

---

## Interfaces You Must Not Break

### `EventEmitter.emit(event: CanonicalEvent) -> bool`
All agent code calls this to push events to the engine. Do not change the signature. The emitter handles gRPC errors internally and returns `False` on failure — agents log it and continue.

### `CanonicalEvent` proto fields set by agents

Agents are responsible for setting these fields before calling `emit()`:

| Field | Who sets it |
|---|---|
| `source` | Agent (`SOURCE_POLYMARKET` or `SOURCE_MMA`) |
| `market_event.*` or `fight_event.*` | Agent |
| `event_id` | **Engine Normalizer** — do not set in agent code |
| `ingested_at` | **Engine Normalizer** — do not set in agent code |

### Delta threshold
`POLYMARKET_DELTA_THRESHOLD` (default `0.01`) is read from env. The agent must not emit events below this threshold — the engine and RAG rely on pre-filtered signal.

---

## Dependencies

| Dependency | Notes |
|---|---|
| `agents/generated/` | Must be generated from proto before running |
| `ENGINE_GRPC_ADDRESS` env var | Where the C++ engine is listening (default `localhost:50051`) |
| `BALLDONTLIE_API_KEY` env var | Optional for free tier; required for GOAT tier |
| `aiohttp` | HTTP client for both APIs |
| `pydantic` | Model validation |
| `grpcio` | gRPC channel to engine |

---

## Run

```bash
# Polymarket agent
python -m agents.polymarket.agent

# MMA agent
python -m agents.mma.agent
```

Both agents run indefinitely. Use `Ctrl+C` / `SIGTERM` to stop — they handle `asyncio.CancelledError` cleanly.

**Key environment variables:**
```bash
ENGINE_GRPC_ADDRESS=localhost:50051
BALLDONTLIE_API_KEY=your_key
POLYMARKET_DELTA_THRESHOLD=0.01
POLYMARKET_POLL_INTERVAL_S=5
MMA_POLL_INTERVAL_S=30
DEBUG_DUMP=1   # optional: dumps raw API JSON to /tmp/polymarket_debug/
```

---

## Tests

**Unit tests (no internet or engine needed — all mocked):**
```bash
pytest agents/tests/unit/ -v
```

**Live API tests (require internet + optional API key):**
```bash
pytest -m api agents/tests/api/ -v
```

The live API tests check:
- Polymarket returns non-empty active markets with prices in [0, 1]
- MMA free tier returns a list (possibly empty if no live events)
- Both GOAT-tier methods raise `NotImplementedError`

When writing new tests, mock `PolymarketClient` and `MMAClient` — never make real HTTP calls in unit tests.

---

## API References

- **Polymarket CLOB API:** https://docs.polymarket.com/api-reference/introduction
- **BallDontLie MMA API:** https://mma.balldontlie.io
  - Free tier: events list, fighter info
  - GOAT tier ($39.99/mo): fight stats (`/fight-statistics`), round stats
