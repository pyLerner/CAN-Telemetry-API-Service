#!/usr/bin/env bash
# Удалённая установка telemetry-client на плату по SSH (rsync + install.sh).
set -euo pipefail

# Пути на удалённом хосте (меняйте здесь при другой раскладке каталогов).
REMOTE_STAGING_DIR="/home/orangepi/telemetry-client"
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

Для шага sudo ./install.sh используется ssh -t (запрос пароля sudo на плате).
Если настроен passwordless sudo для пользователя — пароль не потребуется.

Примеры:
  ./telemetry-client/install-remote.sh orangepi 192.168.1.50
  ./telemetry-client/install-remote.sh orangepi 192.168.1.50 2222

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

_build_ssh() {
  local -n _out=$1
  local _tty="${2:-}"
  _out=(ssh)
  [[ "${_tty}" == "1" ]] && _out+=(-t)
  _out+=(-p "${REMOTE_PORT}")
  if [[ -n "${SSH_OPTS:-}" ]]; then
    # shellcheck disable=SC2206
    _out+=(${SSH_OPTS})
  fi
  _out+=("${REMOTE_USER}@${REMOTE_HOST}")
}

_build_ssh SSH_BASE 0

if [[ -n "${SSH_OPTS:-}" ]]; then
  RSYNC_SSH="ssh -p ${REMOTE_PORT} ${SSH_OPTS}"
else
  RSYNC_SSH="ssh -p ${REMOTE_PORT}"
fi

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
if "${SSH_BASE[@]}" "sudo -n true" 2>/dev/null; then
  "${SSH_BASE[@]}" "cd '${REMOTE_STAGING_DIR}' && sudo ./install.sh"
else
  echo "    Введите пароль sudo пользователя ${REMOTE_USER} на удалённой машине:"
  _build_ssh SSH_TTY 1
  "${SSH_TTY[@]}" "cd '${REMOTE_STAGING_DIR}' && sudo ./install.sh"
fi

echo "==> Статус сервиса"
"${SSH_BASE[@]}" "systemctl --no-pager --full status telemetry-client.service || true"

echo "==> Проверка (при доступном API)"
"${SSH_BASE[@]}" "curl -sf 'http://${REMOTE_API_HOST}:${REMOTE_API_PORT}/api/ping' && echo || echo 'API ping недоступен (клиент всё равно запущен)'"

echo
echo "Готово."
LOCAL_LOG_PATH="$(grep -E '^[[:space:]]*log-path[[:space:]]*=' "${SCRIPT_DIR}/client.ini" | tail -1 | sed 's/^[^=]*=[[:space:]]*//' | tr -d '\r')"
echo "  Лог дверей: ${LOCAL_LOG_PATH}"
echo "  Журнал:     ssh ... journalctl -u telemetry-client -f"
