#!/usr/bin/env bash
set -euo pipefail

# Remote install paths (edit here if your board layout differs).
REMOTE_OPT_DIR="/opt/can-telemetry"
REMOTE_PROJECT_DIR="/home/teamhd/CAN-Telemetry"
REMOTE_SSH_PORT_DEFAULT=22

usage() {
  cat <<'EOF'
Usage: install-remote.sh <user> <host> [port]

Install CAN Telemetry Docker stack on a remote RK3568 host via SSH:
  - rsync project sources
  - install deploy bundle to /opt/can-telemetry
  - build image and start docker compose
  - disable native can-telemetry.service (can0-setup.service is left enabled)

Environment:
  SSH_OPTS   extra ssh options (e.g. -i ~/.ssh/id_rsa)

Example:
  ./docker/install-remote.sh teamhd 192.168.1.50
  ./docker/install-remote.sh teamhd 192.168.1.50 2222
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ $# -lt 2 || $# -gt 3 ]]; then
  usage
  exit 1
fi

REMOTE_USER="$1"
REMOTE_HOST="$2"
REMOTE_PORT="${3:-${REMOTE_SSH_PORT_DEFAULT}}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

SSH_BASE=(ssh -p "${REMOTE_PORT}" "${SSH_OPTS:-}" "${REMOTE_USER}@${REMOTE_HOST}")
RSYNC_SSH="ssh -p ${REMOTE_PORT} ${SSH_OPTS:-}"

echo "==> Remote: ${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_PORT}"
echo "    project dir: ${REMOTE_PROJECT_DIR}"
echo "    opt bundle:  ${REMOTE_OPT_DIR}"

echo "==> Ensure remote project directory exists"
"${SSH_BASE[@]}" "mkdir -p '${REMOTE_PROJECT_DIR}'"

echo "==> Rsync sources to remote"
rsync -az --delete \
  -e "${RSYNC_SSH}" \
  --exclude ".git/" \
  --exclude ".venv/" \
  --exclude "__pycache__/" \
  --exclude ".pytest_cache/" \
  --exclude "logs/" \
  --exclude "docker-exampe/" \
  --exclude "debug/" \
  "${PROJECT_ROOT}/" "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_PROJECT_DIR}/"

echo "==> Install /opt/can-telemetry bundle"
"${SSH_BASE[@]}" "cd '${REMOTE_PROJECT_DIR}' && sudo ./docker/can-telemetry/install-to-opt.sh"

echo "==> Build Docker image on remote"
"${SSH_BASE[@]}" "cd '${REMOTE_PROJECT_DIR}' && ./docker/build-rk3568.sh"

echo "==> Start docker compose"
"${SSH_BASE[@]}" "cd '${REMOTE_PROJECT_DIR}' && docker compose -f docker/docker-compose.yml up -d"

echo "==> Disable native can-telemetry.service (keep can0-setup.service)"
"${SSH_BASE[@]}" "sudo systemctl disable --now can-telemetry.service 2>/dev/null || true"

echo "==> Remote status"
"${SSH_BASE[@]}" "docker compose -f '${REMOTE_PROJECT_DIR}/docker/docker-compose.yml' ps || true"
"${SSH_BASE[@]}" "curl -sf 'http://127.0.0.1:7080/api/ping' || echo 'API ping not ready yet'"

echo "Done."
