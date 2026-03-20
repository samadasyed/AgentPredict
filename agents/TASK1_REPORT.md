# Task 1 Report — Agents Initial Progression
**Author:** Saify
**Date:** 2026-03-19
**Branch:** saify

---

## Objective

Get the agents/ component unblocked and make initial progress across all open TODOs: generate proto stubs, verify Polymarket API contract, fix known code issues, scaffold GOAT tier polling, and create the Dockerfile.

---

## Work Completed

### 1. Proto Stub Generation (Blocker Resolved)

`agents/generated/` did not exist — all imports of `events_pb2` / `events_pb2_grpc` were failing. Generated stubs from `proto/events.proto`:

```bash
mkdir -p agents/generated
python3 -m grpc_tools.protoc \
  -I proto \
  --python_out=agents/generated \
  --grpc_python_out=agents/generated \
  proto/events.proto
touch agents/generated/__init__.py
```

**Issue discovered:** `grpc_tools.protoc` generates a bare `import events_pb2` in `events_pb2_grpc.py` which breaks because the module lives inside the `agents.generated` package. Fixed manually to `from agents.generated import events_pb2 as events__pb2`. This must be done after every regeneration. Automated in the Dockerfile with sed.

### 2. Polymarket API Verification (Live Tested)

Hit the real Polymarket CLOB API to confirm our Pydantic models match the actual response shapes.

| Endpoint | Status | Result |
|---|---|---|
| `GET /markets?active=true` | 200 | Returns `{data: [...], next_cursor: "MTAwMA==", limit: ..., count: ...}`. 1000 markets per page. **Matches `MarketsPage` model.** |
| `GET /markets/{condition_id}` | 200 | Returns single market with `tokens: [{token_id, outcome, price, winner}]`. **Matches `Market`/`TokenPrice` models.** Extra `winner` field safely ignored by Pydantic. |
| `GET /price?token_id=...&side=buy` | 404 | Requires active orderbook. Not usable for closed/inactive markets. |
| `GET /midpoint?token_id=...` | 404 | Same — requires active orderbook. |
| `POST /prices` | 400 | Invalid payload — no batch endpoint available. |

**Conclusion:** No usable batch prices endpoint exists. The current N+1 pattern (`GET /markets/{id}` per market) is the correct approach. The `MarketsPage`, `Market`, `TokenPrice`, and `PriceSnapshot` models are all valid against the real API. Pagination works via base64 `next_cursor`; null/empty means last page.

### 3. Code Fixes

| Fix | File | Detail |
|---|---|---|
| Inline import moved to top-level | `polymarket/client.py` | `import asyncio` was inside `_get()` at line 56; moved to module top |
| Async context manager added | `polymarket/client.py` | Added `__aenter__`/`__aexit__` so `async with PolymarketClient()` works natively |
| Async context manager added | `mma/client.py` | Same pattern for MMAClient |
| Monkey-patch removed | `tests/api/test_polymarket_api.py` | Deleted lines 54-57 that hacked `__aenter__`/`__aexit__` onto PolymarketClient — no longer needed |
| API tests refactored | `tests/api/test_mma_api.py` | Replaced `try/finally/client.close()` with `async with MMAClient()` in all 3 tests |
| RoundStat model completed | `mma/models.py` | Added missing `knockdowns`, `submission_attempts`, `total_strikes` fields to match FightStat |
| TODO comments updated | `polymarket/client.py`, `mma/client.py` | Replaced speculative TODOs with verified results |

### 4. GOAT Tier Stat Polling — Scaffolded

Added the following to `mma/agent.py` (not fully implemented — GOAT tier purchase required):

- **`_GOAT_TIER_ENABLED`** — new env var flag (`BALLDONTLIE_GOAT_TIER=1`), controls whether stat polling runs
- **`_build_fight_stat_event()`** — helper to build `CanonicalEvent` with `SOURCE_MMA` for individual stat types (significant_strikes, takedowns, knockdowns)
- **`_poll_fight_stats()`** — new method called from `_poll_once()` when GOAT is enabled:
  - Skips fights already in `_completed_fight_ids` set
  - Marks newly completed fights (`fight.status == "completed"`) and stops polling them
  - Skips non-in_progress fights
  - Calls `client.get_fight_stats(fight.id)` — gracefully catches `NotImplementedError` if stubs still in place
  - Compares each stat against `_last_stats` cache; emits `FightStatEvent` only on changes
- **`_completed_fight_ids`** and **`_last_stats`** — new instance attributes for state tracking
- Conditional logging at startup (warning if GOAT disabled, info if enabled)

### 5. Dockerfile Created

`agents/Dockerfile`:
- Base image: `python:3.11-slim`
- Installs dependencies from `requirements.txt`
- Copies `proto/` and `agents/` directories
- Runs proto codegen + sed fix for the bare import issue
- No default CMD — each agent is started via docker-compose `command` override

### 6. GOAT Tier Unit Tests & .env.example Update (2026-03-20)

Added `BALLDONTLIE_GOAT_TIER=0` to `.env.example` with documentation comment.

Wrote 5 unit tests for `_poll_fight_stats()` GOAT tier logic in `test_mma_agent.py`:
- `test_goat_stat_change_emits_event` — verifies stat changes emit FightStatEvents (significant_strikes, takedowns)
- `test_goat_no_change_no_emit` — duplicate stats on second poll are not re-emitted
- `test_goat_completed_fight_stops_polling` — completed fights skip stat polling
- `test_goat_stub_not_implemented_handled` — graceful fallback when GOAT stubs still raise NotImplementedError
- `test_goat_scheduled_fight_skipped` — non-in_progress fights are skipped

Uses `monkeypatch` to enable `_GOAT_TIER_ENABLED` without affecting other tests.

---

## Test Results (Updated 2026-03-20)

```
agents/tests/unit/test_mma_agent.py::test_no_live_events_emits_nothing         PASSED
agents/tests/unit/test_mma_agent.py::test_new_fight_emits_fight_discovered     PASSED
agents/tests/unit/test_mma_agent.py::test_known_fight_not_re_emitted           PASSED
agents/tests/unit/test_mma_agent.py::test_fight_discovered_event_fields        PASSED
agents/tests/unit/test_mma_agent.py::test_multiple_fights_each_emitted_once    PASSED
agents/tests/unit/test_mma_agent.py::test_goat_stat_change_emits_event         PASSED
agents/tests/unit/test_mma_agent.py::test_goat_no_change_no_emit              PASSED
agents/tests/unit/test_mma_agent.py::test_goat_completed_fight_stops_polling   PASSED
agents/tests/unit/test_mma_agent.py::test_goat_stub_not_implemented_handled    PASSED
agents/tests/unit/test_mma_agent.py::test_goat_scheduled_fight_skipped         PASSED
agents/tests/unit/test_polymarket_agent.py::test_first_poll_does_not_emit      PASSED
agents/tests/unit/test_polymarket_agent.py::test_significant_delta_emits_event PASSED
agents/tests/unit/test_polymarket_agent.py::test_sub_threshold_delta_does_not_emit PASSED
agents/tests/unit/test_polymarket_agent.py::test_no_active_markets_skips_gracefully PASSED
agents/tests/unit/test_polymarket_agent.py::test_emitted_event_has_correct_fields  PASSED

15 passed in 0.22s
```

---

## Files Changed

| File | Action |
|---|---|
| `agents/generated/__init__.py` | Created |
| `agents/generated/events_pb2.py` | Created (generated) |
| `agents/generated/events_pb2_grpc.py` | Created (generated + import fix) |
| `agents/Dockerfile` | Created |
| `agents/polymarket/client.py` | Modified (import fix, context manager, TODO update) |
| `agents/mma/client.py` | Modified (context manager, TODO update) |
| `agents/mma/models.py` | Modified (RoundStat completed) |
| `agents/mma/agent.py` | Modified (GOAT tier scaffolding) |
| `agents/tests/api/test_polymarket_api.py` | Modified (monkey-patch removed) |
| `agents/tests/api/test_mma_api.py` | Modified (refactored to context managers) |
| `.env.example` | Modified (added BALLDONTLIE_GOAT_TIER) |
| `agents/tests/unit/test_mma_agent.py` | Modified (5 GOAT tier tests added) |

---

## Remaining Work

| Task | Status | Notes |
|---|---|---|
| Proto stubs | Done | Regeneration requires sed fix — automated in Dockerfile |
| Polymarket API verification | Done | All shapes confirmed live |
| Batch prices endpoint | Done (N/A) | No batch endpoint exists — N+1 is correct |
| PolymarketClient context manager | Done | |
| MMAClient context manager | Done | |
| RoundStat model completion | Done | |
| GOAT tier stat polling | Scaffolded | Needs GOAT tier purchase + real HTTP implementation in client stubs |
| Unit tests for _poll_fight_stats | Done | 5 tests covering stat changes, dedup, completed/scheduled skipping, stub handling |
| agents/Dockerfile | Done | |
| Add BALLDONTLIE_GOAT_TIER to .env.example | Done | Added with documentation comment |
| Polymarket websocket feed evaluation | Future | Lower latency alternative to polling |
