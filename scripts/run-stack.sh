#!/usr/bin/env bash
#
# Launch an AgentPredict stack without docker/compose — pure `podman run`
# (or docker). Two ISOLATED stacks can run side by side on one host:
#
#   DEV  — scripts/run-stack.sh mock|real
#          containers apdev-*, network agentpredict_dev_net, images :dev,
#          ports 5173 (dashboard), 8000 (gateway), 50051 (engine).
#          Safe to start/stop/rebuild at will — CANNOT touch production.
#
#   PROD — scripts/run-stack.sh prod   (normally invoked via scripts/deploy.sh)
#          containers ap-*, network agentpredict_net, images :prod,
#          only :8080 published (+ Cloudflare Tunnel when a token is in .env).
#          Confirmation-gated: pass --yes to skip the prompt (deploy.sh does).
#
# Rebuilding :dev images NEVER affects prod — prod containers run :prod tags,
# which only scripts/deploy.sh builds. See handoff/DEV-VS-PROD.md.
#
# Stop with: scripts/stop-stack.sh [dev|prod]   (default: dev)
set -euo pipefail
cd "$(dirname "$0")/.."

MODE="${1:-mock}"
YES="${2:-}"
RUNTIME="${RUNTIME:-}"
if [ -z "$RUNTIME" ]; then
  if command -v podman >/dev/null 2>&1; then RUNTIME=podman
  elif command -v docker >/dev/null 2>&1; then RUNTIME=docker
  else echo "ERROR: neither podman nor docker found" >&2; exit 1; fi
fi

case "$MODE" in
  mock|real)
    PREFIX=apdev
    NET=agentpredict_dev_net
    TAG=dev
    ;;
  prod)
    PREFIX=ap
    NET=agentpredict_net
    TAG=prod
    if [ "$YES" != "--yes" ]; then
      echo "⚠  This (re)starts the PRODUCTION stack behind agentpredictmma.com."
      echo "   Prefer scripts/deploy.sh, which builds :prod images from a clean"
      echo "   tree and verifies health. Continue only if you know why."
      printf "   Type 'prod' to continue: "
      read -r answer
      [ "$answer" = "prod" ] || { echo "aborted."; exit 1; }
    fi
    ;;
  *) echo "usage: run-stack.sh {mock|real|prod} [--yes]"; exit 1;;
esac

ENGINE=agentpredict-engine:$TAG
GATEWAY=agentpredict-gateway:$TAG
AGENTS=agentpredict-agents:$TAG
RAG=agentpredict-rag:$TAG
DASH_DEV=agentpredict-dashboard:dev
DASH_PROD=agentpredict-dashboard:prod

build_if_missing() {  # tag dockerfile context
  if ! $RUNTIME image exists "$1" 2>/dev/null; then
    echo ">> building $1"
    $RUNTIME build -t "$1" -f "$2" "$3"
  fi
}

echo ">> runtime: $RUNTIME   mode: $MODE   stack: $PREFIX-* / $NET / images :$TAG"
build_if_missing "$ENGINE"  engine/Dockerfile        .
build_if_missing "$GATEWAY" gateway/Dockerfile       .
build_if_missing "$AGENTS"  agents/Dockerfile        .
build_if_missing "$RAG"     rag/Dockerfile           .
if [ "$MODE" = "prod" ]; then
  build_if_missing "$DASH_PROD" dashboard/Dockerfile ./dashboard
else
  build_if_missing "$DASH_DEV"  dashboard/Dockerfile.dev ./dashboard
fi

echo ">> resetting $PREFIX-* containers + network"
$RUNTIME rm -f $PREFIX-engine $PREFIX-gateway $PREFIX-rag $PREFIX-pm $PREFIX-mma $PREFIX-dash $PREFIX-tunnel >/dev/null 2>&1 || true
$RUNTIME network exists "$NET" >/dev/null 2>&1 || $RUNTIME network create "$NET" >/dev/null

# Per-mode env for the data-producing services (agents + rag).
if [ "$MODE" = "real" ] || [ "$MODE" = "prod" ]; then
  [ -f .env ] || { echo "ERROR: $MODE mode needs a populated .env (cp .env.example .env)" >&2; exit 1; }
  DATA_ENV=(--env-file .env)              # API keys come from here
  PM_EXTRA=(); MMA_EXTRA=()               # use .env values as-is
else
  DATA_ENV=(-e MOCK_MODE=1)
  PM_EXTRA=(-e POLYMARKET_POLL_INTERVAL_S=3)
  MMA_EXTRA=(-e MMA_POLL_INTERVAL_S=6 -e BALLDONTLIE_GOAT_TIER=1)
fi

# Port exposure: DEV publishes engine gRPC (:50051), gateway (:8000) and the
# Vite dashboard (:5173) for direct access + debugging. PROD keeps everything
# internal except the nginx site (:8080) — the dashboard's nginx proxies /ws
# and /health, and uvicorn runs with --proxy-headers behind it.
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
$RUNTIME run -d --name $PREFIX-engine  --network "$NET" "${ENGINE_PORTS[@]}" \
  -e ENGINE_LOG_LEVEL=INFO -e ENGINE_RING_CAPACITY="${ENGINE_RING_CAPACITY:-16384}" \
  "$ENGINE" >/dev/null

$RUNTIME run -d --name $PREFIX-rag     --network "$NET" \
  "${DATA_ENV[@]}" -e ENGINE_GRPC_ADDRESS=$PREFIX-engine:50051 -e RAG_GRPC_ADDRESS=0.0.0.0:50052 \
  "$RAG" python -m rag.orchestrator >/dev/null

# --network-alias gateway: the prod dashboard's nginx resolves the upstream by
# the name "gateway"; give the container that DNS name on its own network.
$RUNTIME run -d --name $PREFIX-gateway --network "$NET" --network-alias gateway \
  "${GATEWAY_PORTS[@]}" \
  "${DATA_ENV[@]}" -e ENGINE_GRPC_ADDRESS=$PREFIX-engine:50051 -e RAG_GRPC_ADDRESS=$PREFIX-rag:50052 \
  "$GATEWAY" "${GATEWAY_CMD[@]}" >/dev/null

$RUNTIME run -d --name $PREFIX-pm      --network "$NET" \
  "${DATA_ENV[@]}" -e ENGINE_GRPC_ADDRESS=$PREFIX-engine:50051 "${PM_EXTRA[@]}" \
  "$AGENTS" python -m agents.polymarket.agent >/dev/null

$RUNTIME run -d --name $PREFIX-mma     --network "$NET" \
  "${DATA_ENV[@]}" -e ENGINE_GRPC_ADDRESS=$PREFIX-engine:50051 "${MMA_EXTRA[@]}" \
  "$AGENTS" python -m agents.mma.agent >/dev/null

if [ "$MODE" = "prod" ]; then
  $RUNTIME run -d --name $PREFIX-dash  --network "$NET" \
    -p 8080:80 "$DASH_PROD" >/dev/null

  # Publish via Cloudflare Tunnel when a token is configured (.env,
  # CLOUDFLARE_TUNNEL_TOKEN=...). The connector dials OUT to Cloudflare and
  # forwards agentpredictmma.com → ap-dash:80 — no inbound ports needed.
  TUNNEL_TOKEN=$(grep '^CLOUDFLARE_TUNNEL_TOKEN=' .env 2>/dev/null | cut -d= -f2-)
  if [ -n "$TUNNEL_TOKEN" ]; then
    $RUNTIME run -d --name $PREFIX-tunnel --network "$NET" \
      -e TUNNEL_TOKEN="$TUNNEL_TOKEN" \
      docker.io/cloudflare/cloudflared:latest tunnel --no-autoupdate run >/dev/null
    TUNNEL_UP=1
  fi
else
  $RUNTIME run -d --name $PREFIX-dash  --network "$NET" -p 5173:5173 \
    -e VITE_GATEWAY_WS_URL=ws://localhost:8000/ws "$DASH_DEV" >/dev/null
fi

echo
echo "AgentPredict [$MODE] is up ($PREFIX-* on $NET):"
if [ "$MODE" = "prod" ]; then
  echo "  site      → http://localhost:8080   (serves SPA + /ws + /health)"
  if [ "${TUNNEL_UP:-0}" = "1" ]; then
    echo "  public    → Cloudflare Tunnel connector running ($PREFIX-tunnel) → https://agentpredictmma.com"
  else
    echo "  public    → no CLOUDFLARE_TUNNEL_TOKEN in .env — tunnel not started (handoff/DEPLOY.md)"
  fi
else
  echo "  dashboard → http://localhost:5173"
  echo "  gateway   → http://localhost:8000/health"
  echo "  (the production ap-* stack, if running, is untouched)"
fi
echo "  stop with → scripts/stop-stack.sh $([ "$MODE" = prod ] && echo prod || echo dev)"
