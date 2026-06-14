#!/usr/bin/env bash
# remote-task: install-telemetry-client

REMOTE_API_HOST="${REMOTE_API_HOST:-192.168.9.220}"
REMOTE_API_PORT="${REMOTE_API_PORT:-7080}"
REMOTE_OPT_DIR="/opt/telemetry-client"

remote_task() {
  local client_dir="${REPO_ROOT}/telemetry-client"
  [[ -d "${client_dir}" ]] || { echo "Нет каталога ${client_dir}" >&2; return 1; }

  remote_echo "==> Установка telemetry-client"
  remote_echo "    сервис: ${REMOTE_OPT_DIR}"
  remote_mkdir "${REMOTE_STAGING_DIR}"
  remote_echo "==> Rsync telemetry-client"
  remote_rsync "${client_dir}/" "${RSYNC_DEST}" --delete
  remote_echo "==> install.sh"
  remote_sudo "cd '${REMOTE_STAGING_DIR}' && ./install.sh"
  remote_echo "==> Статус"
  remote_ssh "systemctl --no-pager --full status telemetry-client.service || true"
  remote_echo "==> API ping"
  remote_ssh "curl -sf 'http://${REMOTE_API_HOST}:${REMOTE_API_PORT}/api/ping' && echo || echo 'API ping недоступен'"
  remote_echo "Готово."
  remote_journal_hint "telemetry-client.service"
}
