#!/usr/bin/env bash
# Stop and remove the raw-podman AgentPredict stack started by run-stack.sh.
set -uo pipefail
RUNTIME="${RUNTIME:-}"
if [ -z "$RUNTIME" ]; then
  if command -v podman >/dev/null 2>&1; then RUNTIME=podman
  elif command -v docker >/dev/null 2>&1; then RUNTIME=docker
  else echo "ERROR: neither podman nor docker found" >&2; exit 1; fi
fi
$RUNTIME rm -f ap-engine ap-gateway ap-rag ap-pm ap-mma ap-dash ap-tunnel >/dev/null 2>&1 || true
$RUNTIME network rm agentpredict_net >/dev/null 2>&1 || true
echo "AgentPredict stack stopped."
