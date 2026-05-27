#!/usr/bin/env bash
# Установка telemetry-client на плату: файлы в /opt, unit systemd, автозапуск.
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Запускайте от root: sudo $0"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="/opt/telemetry-client"
SYSTEMD_UNIT="/etc/systemd/system/telemetry-client.service"
RUN_USER="teamhd"
RUN_GROUP="teamhd"

echo "[1/5] Install files to ${DEST}"
install -d -m 0755 "${DEST}/etc" "${DEST}/logs"
install -m 0755 "${SCRIPT_DIR}/door_logger.py" "${DEST}/door_logger.py"
if [[ -f "${SCRIPT_DIR}/client.ini" ]]; then
  install -m 0644 "${SCRIPT_DIR}/client.ini" "${DEST}/etc/client.ini"
else
  echo "Ошибка: файл cient.ini не найден в ${SCRIPT_DIR}"
  exit 1
fi
if [[ -f "${SCRIPT_DIR}/client.ini.example" ]]; then
  install -m 0644 "${SCRIPT_DIR}/client.ini.example" "${DEST}/client.ini.example"
fi

echo "[2/5] Install systemd unit"
install -m 0644 "${SCRIPT_DIR}/telemetry-client.service" "${SYSTEMD_UNIT}"

echo "[3/5] Set ownership"
chown -R "${RUN_USER}:${RUN_GROUP}" "${DEST}"

echo "[4/5] Reload systemd"
systemctl daemon-reload

echo "[5/5] Enable and start service"
systemctl enable telemetry-client.service
systemctl restart telemetry-client.service

echo
echo "Installed telemetry-client."
echo "  Door log: ${DEST}/logs/doors.log"
echo "  Journal:  journalctl -u telemetry-client -f"
systemctl --no-pager --full status telemetry-client.service || true
