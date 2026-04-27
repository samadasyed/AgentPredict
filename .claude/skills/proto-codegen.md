---
name: proto-codegen
description: Regenerate Python gRPC stubs in agents/generated/ from proto/events.proto. Use when stubs are missing, events.proto changes, or imports of events_pb2/events_pb2_grpc fail. Includes the mandatory sed fix for the bare-import bug in events_pb2_grpc.py.
---

# Regenerating Python proto stubs

`agents/generated/` is **not checked in** — it must be regenerated locally any time `proto/events.proto` changes, or when starting a fresh checkout. The agents, `rag/`, and `gateway/` all import from `agents.generated`.

## The mandatory sed fix

`grpc_tools.protoc` emits a bare `import events_pb2 as events__pb2` in `events_pb2_grpc.py`. Because the module lives inside the `agents.generated` package, this breaks at import time. The Dockerfile has the fix automated; for local runs it must be re-applied **after every regeneration**.

## Run from project root

```bash
mkdir -p agents/generated
python3 -m grpc_tools.protoc \
  -I proto \
  --python_out=agents/generated \
  --grpc_python_out=agents/generated \
  proto/events.proto
touch agents/generated/__init__.py

# Mandatory: rewrite the bare import so the package resolves.
sed -i '' 's/^import events_pb2 as events__pb2$/from agents.generated import events_pb2 as events__pb2/' \
  agents/generated/events_pb2_grpc.py
```

(On Linux drop the `''` after `-i`.)

## Verify

```bash
python3 -c "from agents.generated import events_pb2, events_pb2_grpc; print(events_pb2.SOURCE_POLYMARKET)"
# Expect: 1
```

## When NOT to regenerate

- Stubs already exist and `proto/events.proto` is unchanged → leave alone.
- Inside Docker — the `agents/Dockerfile` does codegen + sed fix at build time. Don't run protoc manually inside containers.

## Owner notes

The proto file is owned by Samad. Don't modify `proto/events.proto` on the saify branch without coordinating.
