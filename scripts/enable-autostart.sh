#!/usr/bin/env bash
# Enable boot startup for this user's rootless Podman containers.
# Safe to rerun; does not rebuild or replace containers.
set -euo pipefail

ACCOUNT=$(id -un)
SYSTEMD_USER_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)

# Start the user manager at boot, even when nobody logs in, and keep services
# running after logout. Avoid an interactive password prompt during deployment.
loginctl --no-ask-password enable-linger "$ACCOUNT"
if [ "$(loginctl show-user "$ACCOUNT" -p Linger --value)" != "yes" ]; then
  echo "ERROR: lingering must be enabled for $ACCOUNT before production startup." >&2
  exit 1
fi

install -d "$SYSTEMD_USER_DIR/podman-restart.service.d"
install -m 644 "$SCRIPT_DIR/systemd/podman-restart.conf" \
  "$SYSTEMD_USER_DIR/podman-restart.service.d/agentpredict.conf"
systemctl --user daemon-reload
systemctl --user enable --now podman-restart.service
echo ">> automatic startup enabled for $ACCOUNT's Podman containers"
