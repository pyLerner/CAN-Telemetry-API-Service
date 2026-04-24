#!/usr/bin/env bash

set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo ./deploy-can-telemetry.sh"
  exit 1
fi

USER=teamhd
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="/home/${USER}/CAN-Telemetry"
SYSTEMD_DIR="/etc/systemd/system"

echo "[1/6] Sync project to ${APP_DIR}"
mkdir -p "${APP_DIR}"
# rsync -a --delete \
#   --exclude ".git" \
#   --exclude ".venv" \
#   --exclude "__pycache__" \
#   "${SCRIPT_DIR}/" "${APP_DIR}/"

git clone https://github.com/pyLerner/CAN-Telemetry-API-Service.git "${APP_DIR}"

chown -R ${USER}:${USER} "${APP_DIR}"

cd "${APP_DIR}"
git checkout T856
git pull

echo "[2/6] Ensure runtime script is executable"
chmod 755 "${APP_DIR}/can-telemetry.run"

echo "[3/6] Install systemd units"
install -m 644 "${APP_DIR}/can0-setup.service" "${SYSTEMD_DIR}/can0-setup.service"
install -m 644 "${APP_DIR}/can-telemetry.service" "${SYSTEMD_DIR}/can-telemetry.service"

echo "[4/6] Reload systemd"
systemctl daemon-reload

echo "[5/6] Enable units at boot"
systemctl enable can0-setup.service
systemctl enable can-telemetry.service

echo "[6/6] Restart services"
systemctl restart can0-setup.service
systemctl restart can-telemetry.service

echo
echo "Deployment complete."
echo "Service status:"
systemctl --no-pager --full status can0-setup.service can-telemetry.service || true