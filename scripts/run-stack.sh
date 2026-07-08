#!/usr/bin/env bash
#
# Launch the full AgentPredict stack without docker/compose — pure `podman run`
# (or docker, if present). Used as the `make demo` / `make up` fallback on hosts
# that have no compose tool.
#
#   scripts/run-stack.sh mock    # synthetic data, no API keys (default)
#   scripts/run-stack.sh real    # real APIs, reads keys from .env; Vite dev dashboard
#   scripts/run-stack.sh prod    # real APIs + PRODUCTION dashboard: static build
#                                # behind nginx on :8080 (proxies /ws — single
#                                # origin); gateway stays internal. Terminate TLS
#                                # for agentpredictmma.com in front (see
#                                # handoff/DEPLOY.md).
#
# Stop with: scripts/stop-stack.sh
set -euo pipefail
cd "$(dirname "$0")/.."

MODE="${1:-mock}"
RUNTIME="${RUNTIME:-}"
if [ -z "$RUNTIME" ]; then
  if command -v podman >/dev/null 2>&1; then RUNTIME=podman
  elif command -v docker >/dev/null 2>&1; then RUNTIME=docker
  else echo "ERROR: neither podman nor docker found" >&2; exit 1; fi
fi

NET=agentpredict_net
ENGINE=agentpredict-engine:dev
GATEWAY=agentpredict-gateway:dev
AGENTS=agentpredict-agents:dev
RAG=agentpredict-rag:dev
DASH=agentpredict-dashboard:dev
DASH_PROD=agentpredict-dashboard:prod

build_if_missing() {  # tag dockerfile context
  if ! $RUNTIME image exists "$1" 2>/dev/null; then
    echo ">> building $1"
    $RUNTIME build -t "$1" -f "$2" "$3"
  fi
}

echo ">> runtime: $RUNTIME   mode: $MODE"
build_if_missing "$ENGINE"  engine/Dockerfile        .
build_if_missing "$GATEWAY" gateway/Dockerfile       .
build_if_missing "$AGENTS"  agents/Dockerfile        .
build_if_missing "$RAG"     rag/Dockerfile           .
if [ "$MODE" = "prod" ]; then
  build_if_missing "$DASH_PROD" dashboard/Dockerfile ./dashboard
else
  build_if_missing "$DASH"      dashboard/Dockerfile.dev ./dashboard
fi

echo ">> resetting containers + network"
$RUNTIME rm -f ap-engine ap-gateway ap-rag ap-pm ap-mma ap-dash >/dev/null 2>&1 || true
$RUNTIME network exists "$NET" >/dev/null 2>&1 || $RUNTIME network create "$NET" >/dev/null

# Per-mode env for the data-producing services (agents + rag).
if [ "$MODE" = "real" ] || [ "$MODE" = "prod" ]; then
  [ -f .env ] || { echo "ERROR: $MODE mode needs a populated .env (cp .env.example .env)" >&2; exit 1; }
  DATA_ENV=(--env-file .env)              # API keys come from here
  PM_EXTRA=(); MMA_EXTRA=(); RAG_EXTRA=()  # use .env values as-is
else
  DATA_ENV=(-e MOCK_MODE=1)
  PM_EXTRA=(-e POLYMARKET_POLL_INTERVAL_S=3)
  MMA_EXTRA=(-e MMA_POLL_INTERVAL_S=6 -e BALLDONTLIE_GOAT_TIER=1)
  RAG_EXTRA=()
fi

# Port exposure: dev/real modes publish engine gRPC (:50051, host-side probes)
# and the gateway (:8000, direct access + debugging); prod keeps both internal
# (the dashboard's nginx proxies /ws and /health) and runs uvicorn with
# --proxy-headers so client IPs survive the nginx hop.
ENGINE_PORTS=(-p 50051:50051)
GATEWAY_PORTS=(-p 8000:8000)
GATEWAY_CMD=()
if [ "$MODE" = "prod" ]; then
  ENGINE_PORTS=()
  GATEWAY_PORTS=()
  GATEWAY_CMD=(uvicorn gateway.server:app --host 0.0.0.0 --port 8000
               --proxy-headers --forwarded-allow-ips '*')
fi

echo ">> starting services"
$RUNTIME run -d --name ap-engine  --network "$NET" "${ENGINE_PORTS[@]}" \
  -e ENGINE_LOG_LEVEL=INFO -e ENGINE_RING_CAPACITY="${ENGINE_RING_CAPACITY:-16384}" \
  "$ENGINE" >/dev/null

$RUNTIME run -d --name ap-rag     --network "$NET" \
  "${DATA_ENV[@]}" -e ENGINE_GRPC_ADDRESS=ap-engine:50051 -e RAG_GRPC_ADDRESS=0.0.0.0:50052 \
  "${RAG_EXTRA[@]}" "$RAG" python -m rag.orchestrator >/dev/null

# --network-alias gateway: dashboard/nginx.conf resolves the upstream by the
# compose service name "gateway"; give the container that DNS name here too.
$RUNTIME run -d --name ap-gateway --network "$NET" --network-alias gateway \
  "${GATEWAY_PORTS[@]}" \
  "${DATA_ENV[@]}" -e ENGINE_GRPC_ADDRESS=ap-engine:50051 -e RAG_GRPC_ADDRESS=ap-rag:50052 \
  "$GATEWAY" "${GATEWAY_CMD[@]}" >/dev/null

$RUNTIME run -d --name ap-pm      --network "$NET" \
  "${DATA_ENV[@]}" -e ENGINE_GRPC_ADDRESS=ap-engine:50051 "${PM_EXTRA[@]}" \
  "$AGENTS" python -m agents.polymarket.agent >/dev/null

$RUNTIME run -d --name ap-mma     --network "$NET" \
  "${DATA_ENV[@]}" -e ENGINE_GRPC_ADDRESS=ap-engine:50051 "${MMA_EXTRA[@]}" \
  "$AGENTS" python -m agents.mma.agent >/dev/null

if [ "$MODE" = "prod" ]; then
  $RUNTIME run -d --name ap-dash  --network "$NET" \
    -p 8080:80 "$DASH_PROD" >/dev/null
else
  $RUNTIME run -d --name ap-dash  --network "$NET" -p 5173:5173 \
    -e VITE_GATEWAY_WS_URL=ws://localhost:8000/ws "$DASH" >/dev/null
fi

echo
echo "AgentPredict ($MODE) is up:"
if [ "$MODE" = "prod" ]; then
  echo "  site      → http://localhost:8080   (serves SPA + /ws + /health)"
  echo "  TLS       → point your reverse proxy / LB at :8080 (handoff/DEPLOY.md)"
else
  echo "  dashboard → http://localhost:5173"
  echo "  gateway   → http://localhost:8000/health"
fi
echo "  stop with → scripts/stop-stack.sh"
