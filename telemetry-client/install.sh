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
RUN_UID=1000
RUN_GID=1000
CLIENT_INI="${DEST}/etc/client.ini"

_read_ini_log_path() {
  local ini_file="$1"
  grep -E '^[[:space:]]*log-path[[:space:]]*=' "${ini_file}" \
    | tail -1 \
    | sed 's/^[^=]*=[[:space:]]*//' \
    | tr -d '\r'
}

echo "[1/6] Install files to ${DEST}"
install -d -m 0755 "${DEST}/etc"
install -m 0755 "${SCRIPT_DIR}/door_logger.py" "${DEST}/door_logger.py"
if [[ -f "${SCRIPT_DIR}/client.ini" ]]; then
  install -m 0644 "${SCRIPT_DIR}/client.ini" "${CLIENT_INI}"
else
  echo "Ошибка: файл client.ini не найден в ${SCRIPT_DIR}"
  exit 1
fi
if [[ -f "${SCRIPT_DIR}/client.ini.example" ]]; then
  install -m 0644 "${SCRIPT_DIR}/client.ini.example" "${DEST}/client.ini.example"
fi

LOG_PATH="$(_read_ini_log_path "${CLIENT_INI}")"
if [[ -z "${LOG_PATH}" ]]; then
  echo "Ошибка: log-path не найден в ${CLIENT_INI}"
  exit 1
fi
LOG_DIR="$(dirname "${LOG_PATH}")"

echo "[2/6] Create log directory ${LOG_DIR}"
install -d -m 0755 "${LOG_DIR}"
chown -R "${RUN_UID}:${RUN_GID}" "${LOG_DIR}"

echo "[3/6] Install systemd unit"
install -m 0644 "${SCRIPT_DIR}/telemetry-client.service" "${SYSTEMD_UNIT}"

echo "[4/6] Set ownership (${RUN_UID}:${RUN_GID})"
chown -R "${RUN_UID}:${RUN_GID}" "${DEST}"

echo "[5/6] Reload systemd"
systemctl daemon-reload

echo "[6/6] Enable and start service"
systemctl enable telemetry-client.service
systemctl restart telemetry-client.service

echo
echo "Installed telemetry-client."
echo "  Door log: ${LOG_PATH}"
echo "  Journal:  journalctl -u telemetry-client -f"
systemctl --no-pager --full status telemetry-client.service || true
