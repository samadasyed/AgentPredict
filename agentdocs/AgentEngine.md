# Agent Doc — C++ Engine
**Owner:** Samad
**Component:** `engine/`
**Language:** C++20
**Role:** Receives events from both Python agents, validates them, stores them in a ring buffer, and streams them to the gateway and RAG orchestrator over gRPC.

---

## What's Already Done

The full skeleton is implemented and compiles. You should not need to change any interfaces — just fill in the TODOs and create the Dockerfile.

| File | Status |
|---|---|
| `src/normalizer.hpp / .cpp` | Complete — validation logic, UUID stamping, timestamp check |
| `src/event_store.hpp / .cpp` | Complete — ring buffer, cursor reads, condition_variable wait |
| `src/grpc_server.hpp / .cpp` | Complete — both service impls, subscribe loop |
| `src/engine.hpp / .cpp` | Complete — wiring object |
| `src/main.cpp` | Complete — reads `ENGINE_GRPC_ADDRESS` from env |
| `tests/unit/test_normalizer.cpp` | Complete — 14 GTest cases |
| `tests/unit/test_event_store.cpp` | Complete — 10 GTest cases including TSan concurrent test |
| `CMakeLists.txt` | Complete — finds all deps, compiles proto stubs, builds engine_lib |
| `Dockerfile` | **Missing — you need to create this** |

---

## Your TODOs

Search the codebase for `TODO` comments — these are the exact things left for you:

### 1. Create `engine/Dockerfile`
Docker Compose references `engine/Dockerfile`. It needs to:
- Use a base image with CMake, a C++20 compiler, gRPC, Protobuf, and nlohmann_json available
- Build the engine with CMake
- Expose port 50051
- Set `CMD ["./engine"]`

A reasonable base: `ghcr.io/grpc/grpc:latest` or build from `ubuntu:24.04` with `apt install -y cmake g++ libgrpc++-dev protobuf-compiler-grpc nlohmann-json3-dev`.

### 2. UUID library (`src/normalizer.cpp`)
The current `GenerateUUID()` is a minimal in-house implementation using `mt19937_64`. It works correctly but replace it with `libuuid` or `boost::uuid` before production:
```cpp
// TODO: replace with a proper UUID library (e.g. libuuid) in production.
```

### 3. Cursor resume in `Subscribe` (`src/grpc_server.cpp`)
The `SubscribeRequest` has a `cursor` field so clients can resume after a reconnect. Currently ignored:
```cpp
// TODO: parse req->cursor() as uint64 if non-empty for resume support.
uint64_t cursor = store_->CurrentCursor();  // always starts from tail
```
Parse `req->cursor()` as a `uint64_t` when non-empty and pass it as `from_cursor` to `GetSince`.

### 4. TLS + auth (`src/grpc_server.cpp`)
```cpp
// TODO: add TLS credentials and auth interceptor before production deploy.
builder.AddListeningPort(address, grpc::InsecureServerCredentials());
```

### 5. Config from env/flags (`src/main.cpp`)
```cpp
// TODO: parse additional config (ring capacity, log level) from env/flags.
```
Consider reading `RING_CAPACITY` and `LOG_LEVEL` from environment variables.

### 6. EventStore performance (`src/event_store.hpp`)
```cpp
// TODO: evaluate boost::lockfree if profiling shows contention.
```
Run the TSan test first. If profiling reveals writer contention under load, evaluate `boost::lockfree::spsc_queue` for the single-writer path.

---

## Interfaces You Must Not Break

These are consumed by other components. Do not change the signatures or behavior.

### gRPC services (defined in `proto/events.proto`)

```protobuf
service EventIngestion {
  rpc IngestEvent(CanonicalEvent) returns (IngestAck);
  rpc IngestStream(stream CanonicalEvent) returns (IngestAck);
}

service EventStream {
  rpc Subscribe(SubscribeRequest) returns (stream CanonicalEvent);
}
```

- `IngestAck.accepted` must be `false` (not a gRPC error) when validation rejects an event
- `Subscribe` must stream events indefinitely until the client cancels — never return early
- `CanonicalEvent.event_id` and `ingested_at` are always set by the Normalizer — agents do not set these

### Normalizer contract
- `Normalize()` is stateless and thread-safe — must stay that way
- On success: `event_id` is a valid UUID v4 string, `ingested_at` is unix millis at time of call
- On failure: `Result.ok = false`, `Result.error` contains a human-readable reason

### EventStore contract
- `Append()` is the only write path — never expose direct ring access
- `GetSince(cursor)` returns events in insertion order with a monotonically increasing `next_cursor`
- `WaitForNew(cursor, timeout_ms)` returns `true` if new events arrived, `false` on timeout — never throws

---

## Dependencies

| Dependency | Where it comes from |
|---|---|
| `proto/events.proto` | CMake compiles this automatically into `build/generated/` |
| gRPC | System install or vcpkg — must be findable by `find_package(gRPC)` |
| Protobuf | Same as gRPC |
| nlohmann_json | `find_package(nlohmann_json)` |
| GTest | `find_package(GTest)` |

The engine has **no runtime dependency on any Python service.** It only receives connections from agents and gateway — it never calls out.

---

## Build & Run

```bash
cd engine
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j$(nproc)

# Run
ENGINE_GRPC_ADDRESS=0.0.0.0:50051 ./build/engine
```

**With ThreadSanitizer (run before any PR):**
```bash
cmake -B build -DCMAKE_CXX_FLAGS="-fsanitize=thread -g" -DCMAKE_BUILD_TYPE=Debug
cmake --build build -j$(nproc)
cd build && ctest -V
```

---

## Tests

```bash
cd engine/build
ctest -V                        # run all GTest cases
ctest -V -R test_normalizer     # run only normalizer tests
ctest -V -R test_event_store    # run only store tests
```

All 24 tests must pass before merging. The concurrent readers test (`ConcurrentReadsDoNotCrash`) is the most important — it catches data races under TSan.

---

## Port Reference

| Port | Protocol | Direction |
|---|---|---|
| 50051 | gRPC | inbound from polymarket-agent, mma-agent, gateway, rag-orchestrator |
