#!/usr/bin/env bash
# Удалённая установка telemetry-client на плату по SSH (rsync + install.sh).
set -euo pipefail

# Пути на удалённом хосте (меняйте здесь при другой раскладке каталогов).
REMOTE_STAGING_DIR="/home/teamhd/telemetry-client"
REMOTE_OPT_DIR="/opt/telemetry-client"
REMOTE_API_HOST="192.168.9.220"
REMOTE_API_PORT="7080"
REMOTE_SSH_PORT_DEFAULT=22

usage() {
  cat <<'EOF'
Использование: install-remote.sh <user> <host> [port]

Установка telemetry-client на удалённый хост по SSH:
  - rsync каталога telemetry-client на плату
  - sudo ./install.sh (файлы в /opt/telemetry-client, systemd unit)
  - enable и restart telemetry-client.service

Переменные окружения:
  SSH_OPTS   доп. опции ssh (например -i ~/.ssh/id_rsa)

Примеры:
  ./telemetry-client/install-remote.sh teamhd 192.168.1.50
  ./telemetry-client/install-remote.sh teamhd 192.168.1.50 2222

Требования на плате: Python 3.10+, systemd, CAN Telemetry API (по умолчанию ${REMOTE_API_HOST}:${REMOTE_API_PORT}).
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

SSH_BASE=(ssh -p "${REMOTE_PORT}" "${SSH_OPTS:-}" "${REMOTE_USER}@${REMOTE_HOST}")
RSYNC_SSH="ssh -p ${REMOTE_PORT} ${SSH_OPTS:-}"

echo "==> Удалённый хост: ${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_PORT}"
echo "    каталог установки (staging): ${REMOTE_STAGING_DIR}"
echo "    каталог сервиса (после install): ${REMOTE_OPT_DIR}"

echo "==> Создать каталог на удалённой машине"
"${SSH_BASE[@]}" "mkdir -p '${REMOTE_STAGING_DIR}'"

echo "==> Rsync telemetry-client на плату"
rsync -az --delete \
  -e "${RSYNC_SSH}" \
  --exclude "__pycache__/" \
  --exclude "*.pyc" \
  "${SCRIPT_DIR}/" "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_STAGING_DIR}/"

echo "==> Запуск install.sh на удалённой машине"
"${SSH_BASE[@]}" "cd '${REMOTE_STAGING_DIR}' && sudo ./install.sh"

echo "==> Статус сервиса"
"${SSH_BASE[@]}" "systemctl --no-pager --full status telemetry-client.service || true"

echo "==> Проверка (при доступном API)"
"${SSH_BASE[@]}" "curl -sf 'http://${REMOTE_API_HOST}:${REMOTE_API_PORT}/api/ping' && echo || echo 'API ping недоступен (клиент всё равно запущен)'"

echo
echo "Готово."
echo "  Лог дверей: ${REMOTE_OPT_DIR}/logs/doors.log"
echo "  Журнал:     ssh ... journalctl -u telemetry-client -f"
