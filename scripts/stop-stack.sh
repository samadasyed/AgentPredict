#!/usr/bin/env bash
# Stop an AgentPredict stack started by run-stack.sh.
#
#   scripts/stop-stack.sh          # stops the DEV stack (apdev-*) — always safe
#   scripts/stop-stack.sh dev      # same
#   scripts/stop-stack.sh prod     # stops PRODUCTION (ap-*) — confirmation-gated
#   scripts/stop-stack.sh prod --yes
set -uo pipefail

TARGET="${1:-dev}"
YES="${2:-}"
RUNTIME="${RUNTIME:-}"
if [ -z "$RUNTIME" ]; then
  if command -v podman >/dev/null 2>&1; then RUNTIME=podman
  elif command -v docker >/dev/null 2>&1; then RUNTIME=docker
  else echo "ERROR: neither podman nor docker found" >&2; exit 1; fi
fi

case "$TARGET" in
  dev)  PREFIX=apdev; NET=agentpredict_dev_net ;;
  prod)
    PREFIX=ap; NET=agentpredict_net
    if [ "$YES" != "--yes" ]; then
      echo "⚠  This STOPS the PRODUCTION stack — agentpredictmma.com goes down"
      echo "   until 'scripts/run-stack.sh prod' (or scripts/deploy.sh) runs again."
      printf "   Type 'prod' to continue: "
      read -r answer
      [ "$answer" = "prod" ] || { echo "aborted."; exit 1; }
    fi
    ;;
  *) echo "usage: stop-stack.sh [dev|prod] [--yes]"; exit 1;;
esac

$RUNTIME rm -f $PREFIX-engine $PREFIX-gateway $PREFIX-rag $PREFIX-pm $PREFIX-mma $PREFIX-dash $PREFIX-tunnel >/dev/null 2>&1 || true
$RUNTIME network rm "$NET" >/dev/null 2>&1 || true
echo "AgentPredict $TARGET stack stopped."
