# Component: `engine/` — C++20 event engine

Receives events from the agents, validates them, stores them in a ring
buffer, and streams them to subscribers (gateway, RAG). Stateless across
restarts by design — producers re-baseline, so the buffer refills in minutes.

## Pieces (`engine/src/`)

- **`normalizer.*`** — validation + UUID stamping. Rejects events with:
  unknown source, empty `market_id`/`fight_id`, probability outside [0,1],
  or an envelope `timestamp` more than **60 s** from server now
  (`kMaxClockSkewMs`). That last rule is a load-bearing constraint: history
  cannot be streamed as back-dated events; it rides as `history` snapshots.
  Unknown proto fields pass through untouched (proto3 semantics), so adding
  wire fields does not require an engine rebuild — rebuilding just refreshes
  its generated stubs.
- **`event_store.*`** — power-of-2 ring buffer (`ENGINE_RING_CAPACITY`,
  default 4096, prod 16384) with cursor-based reads and condition-variable
  wakeups for streaming subscribers.
- **`grpc_server.*`** — `EventIngestion` (unary + client-stream ingest, ACK
  with rejection reason) and `EventStream.Subscribe` (cursor `""` = live
  tail, `"0"` = full retained replay). Also serves `grpc.health.v1.Health`.

## Build & test

C++ stubs are generated from `proto/events.proto` at image build (CMake +
protoc). 47 GTest cases (incl. a TSan concurrency test):

```bash
cmake --build engine/build --target engine_unit_tests && ctest --test-dir engine/build
```

In this repo's container workflow: `podman exec ap-engine bash -lc '…'`
(see `handoff/RUNBOOK.md`).
