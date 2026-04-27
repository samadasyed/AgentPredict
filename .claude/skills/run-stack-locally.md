---
name: run-stack-locally
description: Bring up the full AgentPredict stack on a dev box without Docker — engine, both agents, RAG orchestrator, gateway, dashboard. Use when testing changes end-to-end, debugging cross-component integration, or before tuning RAG thresholds against real data.
---

# Run the full stack locally (no Docker)

Six processes total. Start order matters because of gRPC dependencies.

## 0. Prerequisites

```bash
# Python deps
pip install -r requirements.txt

# Generate proto stubs (see proto-codegen skill for the full sed fix)
python3 -m grpc_tools.protoc -I proto --python_out=agents/generated --grpc_python_out=agents/generated proto/events.proto
touch agents/generated/__init__.py
sed -i '' 's/^import events_pb2 as events__pb2$/from agents.generated import events_pb2 as events__pb2/' agents/generated/events_pb2_grpc.py

# .env populated with at minimum: GOOGLE_API_KEY, PINECONE_API_KEY, BALLDONTLIE_API_KEY (free-tier ok)
cp .env.example .env  # then edit
```

## 1. C++ engine (port 50051) — **start first**

```bash
cd engine
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j$(sysctl -n hw.ncpu 2>/dev/null || nproc)
ENGINE_GRPC_ADDRESS=0.0.0.0:50051 ./build/engine
```

Healthy log: `[engine] gRPC listening on 0.0.0.0:50051`. Keep this terminal open.

## 2. Polymarket + MMA agents (separate terminals)

```bash
# Terminal 2
ENGINE_GRPC_ADDRESS=localhost:50051 \
POLYMARKET_POLL_INTERVAL_S=5 \
POLYMARKET_DELTA_THRESHOLD=0.01 \
python -m agents.polymarket.agent

# Terminal 3
ENGINE_GRPC_ADDRESS=localhost:50051 \
MMA_POLL_INTERVAL_S=30 \
python -m agents.mma.agent
```

Healthy log: `[polymarket-agent] starting — interval=5.0s delta_threshold=0.010`; `[mma-agent] starting — interval=30.0s`. MMA logs a GOAT-tier warning — that's expected on free tier.

## 3. RAG orchestrator (port 50052)

```bash
# Terminal 4
ENGINE_GRPC_ADDRESS=localhost:50051 \
RAG_GRPC_ADDRESS=0.0.0.0:50052 \
python -m rag.orchestrator
```

Healthy log: `[orchestrator] RagStream gRPC server on 0.0.0.0:50052` and `[orchestrator] subscribing to engine at localhost:50051`.

## 4. Gateway (port 8000)

```bash
# Terminal 5
ENGINE_GRPC_ADDRESS=localhost:50051 \
RAG_GRPC_ADDRESS=localhost:50052 \
uvicorn gateway.server:app --host 0.0.0.0 --port 8000
```

Verify: `curl http://localhost:8000/health` → `{"status": "ok", "ws_clients": 0}`.

## 5. Dashboard (port 5173)

```bash
# Terminal 6
cd dashboard
npm install   # only first time
npm run dev
```

Open `http://localhost:5173`. The header should show ● connected once the WebSocket attaches.

## End-to-end smoke test

1. Both columns initially read "Waiting for events…"
2. Polymarket events appear left within ~5s if any UFC market is active
3. RAG predictions appear right only on market deltas ≥ 2% — for visible activity, drop `_MEANINGFUL_DELTA_THRESHOLD` in `rag/orchestrator.py` to `0.005` temporarily

## Shutdown

`Ctrl+C` each terminal in **reverse** order (dashboard → gateway → rag → agents → engine). Each handles `SIGTERM` cleanly.

## When to skip and use Docker instead

If you're testing the production wiring (network names, healthchecks, env injection), use `docker compose up --build`. The 6 Dockerfiles still need finishing — `engine/Dockerfile`, `rag/Dockerfile`, `gateway/Dockerfile`, `dashboard/Dockerfile.dev` are TODO; only `agents/Dockerfile` is done.
