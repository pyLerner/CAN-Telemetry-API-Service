#!/usr/bin/env bash
# Библиотека удалённого SSH/rsync. Подключать через source, не запускать напрямую.
# shellcheck shell=bash

REMOTE_SSH_PORT_DEFAULT="${REMOTE_SSH_PORT_DEFAULT:-22}"
REMOTE_STAGING_FALLBACK_USER="${REMOTE_STAGING_FALLBACK_USER:-orangepi}"
REMOTE_STAGING_SUBDIR="${REMOTE_STAGING_SUBDIR:-telemetry-client}"

USE_SSH_CONFIG=0
SSH_TARGET=""
REMOTE_USER=""
REMOTE_HOST=""
REMOTE_PORT=""
REMOTE_STAGING_DIR=""
RSYNC_DEST=""
RSYNC_SSH=""
REMOTE_DRY_RUN=0

SSH_BASE=()

remote__ssh_g_value() {
  awk -v k="$1" '$1 == k { v = $2 } END { print v }'
}

remote__ssh_config_has_host() {
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

remote__resolve_ssh_config_host() {
  local alias="$1"
  local ssh_g user hostname port

  if ! ssh_g="$(ssh -G "${alias}" 2>/dev/null)"; then
    echo "Ошибка: не удалось разобрать Host '${alias}' (ssh -G)" >&2
    return 1
  fi

  hostname="$(printf '%s\n' "${ssh_g}" | remote__ssh_g_value hostname)"
  if [[ -z "${hostname}" ]]; then
    echo "Ошибка: Host '${alias}' не найден в SSH config (~/.ssh/config)" >&2
    return 1
  fi
  if [[ "${hostname}" == "${alias}" ]] && ! remote__ssh_config_has_host "${alias}"; then
    echo "Ошибка: Host '${alias}' не найден в SSH config (~/.ssh/config)" >&2
    return 1
  fi

  user="$(printf '%s\n' "${ssh_g}" | remote__ssh_g_value user)"
  port="$(printf '%s\n' "${ssh_g}" | remote__ssh_g_value port)"
  [[ -z "${user}" ]] && user="${REMOTE_STAGING_FALLBACK_USER}"
  [[ -z "${port}" ]] && port="${REMOTE_SSH_PORT_DEFAULT}"

  REMOTE_USER="${user}"
  REMOTE_HOST="${hostname}"
  REMOTE_PORT="${port}"
  REMOTE_STAGING_DIR="/home/${user}/${REMOTE_STAGING_SUBDIR}"
}

remote_parse_target() {
  local argc=$#
  if [[ "${argc}" -eq 1 ]]; then
    USE_SSH_CONFIG=1
    SSH_TARGET="$1"
    remote__resolve_ssh_config_host "${SSH_TARGET}"
  elif [[ "${argc}" -eq 2 || "${argc}" -eq 3 ]]; then
    USE_SSH_CONFIG=0
    REMOTE_USER="$1"
    REMOTE_HOST="$2"
    REMOTE_PORT="${3:-${REMOTE_SSH_PORT_DEFAULT}}"
    REMOTE_STAGING_DIR="/home/${REMOTE_USER}/${REMOTE_STAGING_SUBDIR}"
  else
    echo "Ошибка: укажите <Host> или <user> <host> [port]" >&2
    return 1
  fi
}

remote_set_staging_subdir() {
  REMOTE_STAGING_SUBDIR="$1"
  if [[ -n "${REMOTE_USER:-}" ]]; then
    REMOTE_STAGING_DIR="/home/${REMOTE_USER}/${REMOTE_STAGING_SUBDIR}"
  fi
}

remote_build_ssh() {
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

remote_init_transport() {
  remote_build_ssh SSH_BASE 0
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

remote_print_info() {
  if [[ "${USE_SSH_CONFIG}" -eq 1 ]]; then
    echo "==> Удалённый хост (SSH config): Host ${SSH_TARGET}"
    echo "    разрешено: ${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_PORT}"
  else
    echo "==> Удалённый хост: ${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_PORT}"
  fi
  echo "    staging: ${REMOTE_STAGING_DIR}"
}

remote_echo() {
  echo "$@"
}

remote_ssh() {
  local cmd="$1"
  if [[ "${REMOTE_DRY_RUN}" -eq 1 ]]; then
    echo "[dry-run] ssh: ${cmd}"
    return 0
  fi
  remote_build_ssh _ssh 0
  "${_ssh[@]}" "${cmd}"
}

remote_mkdir() {
  remote_ssh "mkdir -p '$1'"
}

remote_scp() {
  local local_file="$1"
  local remote_path="$2"
  local dest
  local -a _scp=(scp)

  if [[ "${REMOTE_DRY_RUN}" -eq 1 ]]; then
    echo "[dry-run] scp: ${local_file} -> ${remote_path}"
    return 0
  fi

  if [[ "${USE_SSH_CONFIG}" -eq 1 ]]; then
    if [[ -n "${SSH_OPTS:-}" ]]; then
      # shellcheck disable=SC2206
      _scp+=(${SSH_OPTS})
    fi
    dest="${SSH_TARGET}:${remote_path}"
  else
    _scp+=(-P "${REMOTE_PORT}")
    if [[ -n "${SSH_OPTS:-}" ]]; then
      # shellcheck disable=SC2206
      _scp+=(${SSH_OPTS})
    fi
    dest="${REMOTE_USER}@${REMOTE_HOST}:${remote_path}"
  fi

  "${_scp[@]}" "${local_file}" "${dest}"
}

remote_rsync() {
  local src="$1"
  local dest_path="${2:-${RSYNC_DEST}}"
  local -a rsync_args=( -az )
  if [[ "${3:-}" == "--delete" ]]; then
    rsync_args+=( --delete )
  fi
  if [[ "${REMOTE_DRY_RUN}" -eq 1 ]]; then
    echo "[dry-run] rsync ${rsync_args[*]} -e '${RSYNC_SSH}' '${src}' '${dest_path}'"
    return 0
  fi
  rsync "${rsync_args[@]}" \
    -e "${RSYNC_SSH}" \
    --exclude "__pycache__/" \
    --exclude "*.pyc" \
    "${src}" "${dest_path}"
}

remote_sudo() {
  local cmd="$1"
  local quoted_cmd
  printf -v quoted_cmd '%q' "${cmd}"
  # Цепочки с && должны выполняться целиком под sudo (не «sudo cmd1 && cmd2»).
  local sudo_cmd="sudo sh -c ${quoted_cmd}"

  # #region agent log
  printf '{"sessionId":"f1ee75","hypothesisId":"C","location":"remote-ssh.sh:remote_sudo","message":"sudo wrapper","data":{"uses_sh_c":true,"cmd_len":%s},"timestamp":%s}\n' \
    "${#cmd}" "$(date +%s%3N)" \
    >> "/home/pyler/Projects/Infoteh/Infoteh-Main-Project/projects/CAN-Telemetry-API-Service/.cursor/debug-f1ee75.log" 2>/dev/null || true
  # #endregion

  if [[ "${REMOTE_DRY_RUN}" -eq 1 ]]; then
    echo "[dry-run] ${sudo_cmd}"
    return 0
  fi
  remote_build_ssh _ssh 0
  if "${_ssh[@]}" "sudo -n true" 2>/dev/null; then
    "${_ssh[@]}" "${sudo_cmd}"
  else
    echo "    Введите пароль sudo пользователя ${REMOTE_USER} на удалённой машине:"
    remote_build_ssh _ssh_tty 1
    "${_ssh_tty[@]}" "${sudo_cmd}"
  fi
}

remote_journal_hint() {
  if [[ "${USE_SSH_CONFIG}" -eq 1 ]]; then
    echo "  Журнал:     ssh ${SSH_TARGET} journalctl -u $1 -f"
  else
    echo "  Журнал:     ssh -p ${REMOTE_PORT} ${REMOTE_USER}@${REMOTE_HOST} journalctl -u $1 -f"
  fi
}
