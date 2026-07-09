#!/usr/bin/env bash
#
# Promote the current checkout to PRODUCTION (agentpredictmma.com).
# This is the ONLY supported path to prod. What it does, in order:
#
#   1. Guardrails: refuses a dirty working tree (--dirty overrides);
#      requires typed confirmation (--yes overrides, for automation).
#   2. Builds all :prod images from THIS commit (dev's :dev tags are never
#      used in prod) and labels them with the git SHA.
#   3. Restarts the prod stack (ap-*, network agentpredict_net, :8080 +
#      Cloudflare Tunnel). ~30-60s of downtime while containers swap.
#   4. Verifies: local /health must go green; prints the public check.
#   5. Prunes dangling image layers (small disk).
#
#   scripts/deploy.sh [--yes] [--dirty]
#
# See handoff/DEV-VS-PROD.md for the full dev-vs-prod workflow.
set -euo pipefail
cd "$(dirname "$0")/.."

RUNTIME="${RUNTIME:-}"
if [ -z "$RUNTIME" ]; then
  if command -v podman >/dev/null 2>&1; then RUNTIME=podman
  elif command -v docker >/dev/null 2>&1; then RUNTIME=docker
  else echo "ERROR: neither podman nor docker found" >&2; exit 1; fi
fi

YES=0; DIRTY_OK=0
for arg in "$@"; do
  case "$arg" in
    --yes) YES=1;;
    --dirty) DIRTY_OK=1;;
    *) echo "usage: deploy.sh [--yes] [--dirty]"; exit 1;;
  esac
done

# ── Guardrail 1: deploy only committed code ──────────────────────────────────
SHA=$(git rev-parse --short HEAD)
BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [ "$DIRTY_OK" != "1" ] && [ -n "$(git status --porcelain)" ]; then
  echo "✗ Working tree has uncommitted changes — prod deploys must come from"
  echo "  a commit (so the site is always reproducible from git history)."
  echo "  Commit your work, or override with --dirty if you really mean it."
  exit 1
fi

# ── Guardrail 2: a human said so ─────────────────────────────────────────────
echo "Deploying to PRODUCTION (agentpredictmma.com)"
echo "  commit : $SHA ($BRANCH)$( [ -n "$(git status --porcelain)" ] && echo '  +UNCOMMITTED CHANGES')"
echo "  images : agentpredict-{engine,gateway,agents,rag,dashboard}:prod"
echo "  outage : ~30-60s while containers swap"
if [ "$YES" != "1" ]; then
  printf "Type 'deploy' to continue: "
  read -r answer
  [ "$answer" = "deploy" ] || { echo "aborted."; exit 1; }
fi

# ── Build :prod images from this checkout (serial — small host) ──────────────
LABEL="--label=org.agentpredict.git-sha=$SHA"
echo ">> building :prod images @ $SHA"
$RUNTIME build $LABEL -q -t agentpredict-engine:prod    -f engine/Dockerfile        .
$RUNTIME build $LABEL -q -t agentpredict-gateway:prod   -f gateway/Dockerfile       .
$RUNTIME build $LABEL -q -t agentpredict-agents:prod    -f agents/Dockerfile        .
$RUNTIME build $LABEL -q -t agentpredict-rag:prod       -f rag/Dockerfile           .
$RUNTIME build $LABEL -q -t agentpredict-dashboard:prod -f dashboard/Dockerfile     ./dashboard

# ── Swap the prod stack ──────────────────────────────────────────────────────
scripts/stop-stack.sh prod --yes
scripts/run-stack.sh prod --yes

# ── Verify ───────────────────────────────────────────────────────────────────
echo ">> waiting for local health (via the prod nginx on :8080)…"
ok=0
for i in $(seq 1 30); do
  if curl -sf --max-time 5 http://localhost:8080/health 2>/dev/null | grep -q '"status":\s*"ok"'; then
    ok=1; break
  fi
  sleep 4
done
if [ "$ok" != "1" ]; then
  echo "✗ /health did not go green within 2 minutes — investigate:"
  echo "    $RUNTIME logs ap-gateway | tail -30"
  echo "    $RUNTIME logs ap-engine  | tail -30"
  exit 1
fi

$RUNTIME image prune -f >/dev/null || true
echo
echo "✓ Production is serving commit $SHA"
echo "  local  : http://localhost:8080"
echo "  public : curl -s https://agentpredictmma.com/health   (verify from outside)"
