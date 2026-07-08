# Runbook — build, run, test, debug

Everything here is tuned to **this machine**: Fedora host with only Python 3.14,
no sudo, no docker daemon, no node, no system protoc — but **rootless podman 5.x
with networking works**, so everything builds and runs in containers.

## Run the stack

```bash
scripts/run-stack.sh mock          # synthetic demo data, no API keys
scripts/run-stack.sh real          # real APIs, needs populated .env (dev dashboard)
scripts/run-stack.sh prod          # real APIs + production dashboard (nginx :8080,
                                   #   single origin, gateway internal) — see DEPLOY.md
scripts/stop-stack.sh              # tear down containers + network
```

(`make demo` / `make up` / `make down` wrap the same scripts when no compose tool
exists, which is the case here. `RUNTIME=podman` is auto-detected.)

- Containers: `ap-engine ap-gateway ap-rag ap-pm ap-mma ap-dash` on network
  `agentpredict_net`. Logs: `podman logs -f ap-<name>`.
- Dashboard: `http://localhost:5173` · Gateway health: `http://localhost:8000/health`
- From Samad's laptop (server has no browser):
  `ssh -N -L 5173:localhost:5173 -L 8000:localhost:8000 samad@100.91.26.104`
- Terminal-only stream watch (no browser): `make watch`
  (runs `scripts/watch-stream.py` against `ws://localhost:8000/ws`).
- **The script only builds images that don't exist** (`build_if_missing`) — after
  a code change you must rebuild the image yourself (below), then re-run the script.
- Real mode needs `.env` (copy from `.env.example`). Keys live only in `.env`,
  which is gitignored — **never commit it, never echo key values**. Without
  `GOOGLE_API_KEY`/`PINECONE_API_KEY` the rag container exits at startup (keys are
  read at module import).

## Rebuild after code changes

```bash
# engine / gateway / agents / rag — repo-root context (Dockerfiles resolve ../proto)
podman build -t agentpredict-agents:dev  -f agents/Dockerfile  .
podman build -t agentpredict-engine:dev  -f engine/Dockerfile  .
podman build -t agentpredict-gateway:dev -f gateway/Dockerfile .
podman build -t agentpredict-rag:dev     -f rag/Dockerfile     .
# dashboard — its own context
podman build -t agentpredict-dashboard:dev -f dashboard/Dockerfile.dev ./dashboard
```

Then `scripts/stop-stack.sh && scripts/run-stack.sh <mode>`. Tip: when
backgrounding a build, make `podman build` the last command in the shell line or
the exit-code notification lies.

## Regenerate proto stubs (after editing `proto/events.proto`)

Python stubs are **checked in** at `agents/generated/`. Regenerate in a container
(host Python 3.14 can't install the pinned toolchain):

```bash
podman run --rm -v "$PWD":/w:z -w /w python:3.11-slim bash -c '
  pip install -q grpcio-tools==1.65.1 protobuf==5.27.2 &&
  python -m grpc_tools.protoc -I proto \
    --python_out=agents/generated --grpc_python_out=agents/generated \
    proto/events.proto'
# grpc_tools emits a broken absolute import — fix it:
sed -i 's/^import events_pb2 as events__pb2$/from agents.generated import events_pb2 as events__pb2/' \
  agents/generated/events_pb2_grpc.py
```

C++ stubs regenerate automatically when the engine image builds (CMake/protoc).
Also update the TS mirror types in `dashboard/src/types/events.ts` by hand.

## Tests

### Python (agents + rag + gateway) — host venv, currently 109 tests
```bash
python3 -m venv .venv-test   # once; self-gitignores
.venv-test/bin/pip install pytest pytest-asyncio pytest-mock fastapi aiohttp \
  pydantic grpcio "protobuf>=5.26,<6" google-generativeai pinecone websockets
PINECONE_API_KEY=fake GOOGLE_API_KEY=fake PINECONE_INDEX_NAME=agentpredict \
  .venv-test/bin/pytest agents/tests/unit rag/tests/unit gateway/tests/unit
```
The dummy keys are required **up front**: rag modules read keys at import time.
Install `pinecone`, not `pinecone-client` (the latter is a tombstone that raises).

### C++ engine — 47 tests, run inside the engine container
```bash
podman exec ap-engine bash -lc \
  'cmake --build /app/engine/build --target engine_unit_tests -j$(nproc) &&
   cd /app/engine/build && ctest --output-on-failure'
```

### Dashboard — 42 vitest tests + tsc, in a node container (no host node)
```bash
podman run --rm -v "$PWD/dashboard":/app:z -w /app node:20-slim bash -c \
  'npm install --no-audit --no-fund >/dev/null && npx vitest run && npx tsc --noEmit'
```

## Visual verification (no browser on the host)

- `scripts/shoot.py` screenshots the dashboard via Chrome DevTools Protocol
  (headless chromium in a container). A full-page variant lived at
  `/tmp/shoot_full.py` — same script plus `captureBeyondViewport: True` in the
  `Page.captureScreenshot` params; recreate it from `shoot.py` if `/tmp` was wiped.
- WebSocket probe pattern that works: connect to `ws://localhost:8000/ws`, read
  messages until a **wall-clock deadline** (`deadline = time.monotonic() + 18`) —
  per-message timeouts never fire while events flow, and the probe hangs forever.

## Troubleshooting map

| Symptom | Likely cause / fix |
|---|---|
| Dashboard empty, gateway `/health` 200 | Data plane dead in gateway conversion — check `podman logs ap-gateway` for MessageToDict TypeError; the one call site is `gateway/proto_utils.py` (protobuf-5 kwarg). Run `gateway/tests/unit/test_proto_utils.py` after any protobuf bump |
| Mock mode shows no markets | Mock market `question` must contain "UFC" (the `POLYMARKET_QUERY` filter applies in mock mode too — this regressed once) |
| Real mode shows no markets | Usually genuine: no UFC markets listed yet (`podman logs ap-pm` says "no on-theme (UFC) markets"). Off-theme fallback is opt-in via `POLYMARKET_FALLBACK_ALL=1` |
| Upcoming cards appear as "live" with empty scoreboards | A sentinel stat leaked past a filter — check `SENTINEL_STATS` (dashboard) and `_SENTINEL_STATS` (rag) cover every sentinel stat_type |
| RAG spams nonsense predictions every ~30s | Sentinels reaching `_is_meaningful` — same fix as above; restart `ap-gateway` to flush buffered predictions |
| Engine silently drops events | Normalizer validation: source ≠ SOURCE_UNKNOWN, market_id non-empty, probability ∈ [0,1], envelope timestamp within **60s** of now (never back-date events; use the `history` field) |
| 401 from BallDontLie `/fights` or `/fight_stats` | Plan-gated (needs GOAT tier) — expected on the current key; not a bug |
| Podman bind-mount permission errors | Add `:z` to the volume flag (SELinux) |

## Git conventions

- Work and commit on the **`samad`** branch; never commit to `main`; **don't push
  unless asked**. Samad reviews/pushes.
- `.env`, `*.pem`, `*.key`, `secrets/` are gitignored and must stay out of git;
  `.env.example` is the tracked template. `dashboard/node_modules` is ignored via
  `dashboard/.gitignore`.
