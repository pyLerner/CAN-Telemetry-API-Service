#!/usr/bin/env bash
# Удалённая установка telemetry-client на плату по SSH (rsync + install.sh).
set -euo pipefail

REMOTE_OPT_DIR="/opt/telemetry-client"
REMOTE_API_HOST="192.168.9.220"
REMOTE_API_PORT="7080"
REMOTE_SSH_PORT_DEFAULT=22
REMOTE_STAGING_FALLBACK_USER="orangepi"

USE_SSH_CONFIG=0
SSH_TARGET=""
REMOTE_USER=""
REMOTE_HOST=""
REMOTE_PORT=""
REMOTE_STAGING_DIR=""
RSYNC_DEST=""

usage() {
  cat <<EOF
Использование:
  install-remote.sh <Host>                    Host из ~/.ssh/config
  install-remote.sh <user> <host> [port]      явные user, host и порт SSH

Установка telemetry-client на удалённый хост:
  - rsync каталога telemetry-client на плату
  - sudo ./install.sh (файлы в /opt/telemetry-client, systemd unit)
  - enable и restart telemetry-client.service

В режиме <Host> OpenSSH подставляет User, HostName, Port, IdentityFile и др. из config.
Staging: /home/<User>/telemetry-client (User из ssh -G).

Переменные окружения:
  SSH_OPTS   доп. опции ssh (например -i ~/.ssh/id_rsa)

Для шага sudo ./install.sh используется ssh -t (запрос пароля sudo на плате).
Если настроен passwordless sudo — пароль не потребуется.

Примеры:
  ./telemetry-client/install-remote.sh board-orange
  ./telemetry-client/install-remote.sh orangepi 192.168.1.50
  ./telemetry-client/install-remote.sh orangepi 192.168.1.50 2222

Требования на плате: Python 3.10+, systemd, CAN Telemetry API (по умолчанию ${REMOTE_API_HOST}:${REMOTE_API_PORT}).
EOF
}

_ssh_g_value() {
  local key="$1"
  awk -v k="$key" '$1 == k { v = $2 } END { print v }'
}

_ssh_config_has_host() {
  local alias="$1"
  local f
  for f in "${HOME}/.ssh/config" "${HOME}/.ssh/config.d/"*; do
    [[ -f "${f}" ]] || continue
    if grep -qE "^[Hh]ost[[:space:]]+.*(^|[[:space:]])${alias}([[:space:]]|$)" "${f}"; then
      return 0
    fi
  done
  return 1
}

_resolve_ssh_config_host() {
  local alias="$1"
  local ssh_g user hostname port

  if ! ssh_g="$(ssh -G "${alias}" 2>/dev/null)"; then
    echo "Ошибка: не удалось разобрать Host '${alias}' (ssh -G)" >&2
    exit 1
  fi

  hostname="$(printf '%s\n' "${ssh_g}" | _ssh_g_value hostname)"
  if [[ -z "${hostname}" ]]; then
    echo "Ошибка: Host '${alias}' не найден в SSH config (~/.ssh/config)" >&2
    exit 1
  fi
  if [[ "${hostname}" == "${alias}" ]] && ! _ssh_config_has_host "${alias}"; then
    echo "Ошибка: Host '${alias}' не найден в SSH config (~/.ssh/config)" >&2
    exit 1
  fi

  user="$(printf '%s\n' "${ssh_g}" | _ssh_g_value user)"
  port="$(printf '%s\n' "${ssh_g}" | _ssh_g_value port)"
  [[ -z "${user}" ]] && user="${REMOTE_STAGING_FALLBACK_USER}"
  [[ -z "${port}" ]] && port="${REMOTE_SSH_PORT_DEFAULT}"

  REMOTE_USER="${user}"
  REMOTE_HOST="${hostname}"
  REMOTE_PORT="${port}"
  REMOTE_STAGING_DIR="/home/${user}/telemetry-client"
}

_build_ssh() {
  local -n _out=$1
  local _tty="${2:-}"
  _out=(ssh)
  [[ "${_tty}" == "1" ]] && _out+=(-t)
  if [[ "${USE_SSH_CONFIG}" -eq 1 ]]; then
    if [[ -n "${SSH_OPTS:-}" ]]; then
      # shellcheck disable=SC2206
      _out+=(${SSH_OPTS})
    fi
    _out+=("${SSH_TARGET}")
  else
    _out+=(-p "${REMOTE_PORT}")
    if [[ -n "${SSH_OPTS:-}" ]]; then
      # shellcheck disable=SC2206
      _out+=(${SSH_OPTS})
    fi
    _out+=("${REMOTE_USER}@${REMOTE_HOST}")
  fi
}

_setup_rsync() {
  if [[ "${USE_SSH_CONFIG}" -eq 1 ]]; then
    if [[ -n "${SSH_OPTS:-}" ]]; then
      RSYNC_SSH="ssh ${SSH_OPTS}"
    else
      RSYNC_SSH="ssh"
    fi
    RSYNC_DEST="${SSH_TARGET}:${REMOTE_STAGING_DIR}/"
  else
    if [[ -n "${SSH_OPTS:-}" ]]; then
      RSYNC_SSH="ssh -p ${REMOTE_PORT} ${SSH_OPTS}"
    else
      RSYNC_SSH="ssh -p ${REMOTE_PORT}"
    fi
    RSYNC_DEST="${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_STAGING_DIR}/"
  fi
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ $# -eq 1 ]]; then
  USE_SSH_CONFIG=1
  SSH_TARGET="$1"
  _resolve_ssh_config_host "${SSH_TARGET}"
elif [[ $# -eq 2 || $# -eq 3 ]]; then
  USE_SSH_CONFIG=0
  REMOTE_USER="$1"
  REMOTE_HOST="$2"
  REMOTE_PORT="${3:-${REMOTE_SSH_PORT_DEFAULT}}"
  REMOTE_STAGING_DIR="/home/${REMOTE_USER}/telemetry-client"
else
  usage
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

_build_ssh SSH_BASE 0
_setup_rsync

if [[ "${USE_SSH_CONFIG}" -eq 1 ]]; then
  echo "==> Удалённый хост (SSH config): Host ${SSH_TARGET}"
  echo "    разрешено: ${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_PORT}"
else
  echo "==> Удалённый хост: ${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_PORT}"
fi
echo "    каталог установки (staging): ${REMOTE_STAGING_DIR}"
echo "    каталог сервиса (после install): ${REMOTE_OPT_DIR}"

echo "==> Создать каталог на удалённой машине"
"${SSH_BASE[@]}" "mkdir -p '${REMOTE_STAGING_DIR}'"

echo "==> Rsync telemetry-client на плату"
rsync -az --delete \
  -e "${RSYNC_SSH}" \
  --exclude "__pycache__/" \
  --exclude "*.pyc" \
  "${SCRIPT_DIR}/" "${RSYNC_DEST}"

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
if [[ "${USE_SSH_CONFIG}" -eq 1 ]]; then
  echo "  Журнал:     ssh ${SSH_TARGET} journalctl -u telemetry-client -f"
else
  echo "  Журнал:     ssh -p ${REMOTE_PORT} ${REMOTE_USER}@${REMOTE_HOST} journalctl -u telemetry-client -f"
fi
