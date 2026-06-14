#!/usr/bin/env bash
set -euo pipefail

REMOTE_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/lib" && pwd)"
REMOTE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REMOTE_TASKS_DIR="${REMOTE_ROOT}/tasks"
REPO_ROOT="$(cd "${REMOTE_ROOT}/../.." && pwd)"

REMOTE_DRY_RUN=0
LIST_TASKS=0
REMOTE_CLI_ARGS=()
TASK_FILE=""
TARGET_ARGC=0
TASK_ARGS=()

usage() {
  cat <<EOF
Использование:
  remote-run.sh [опции] <target> <task-file> [task-args...]
  remote-run.sh [опции] <user> <host> [port] <task-file> [task-args...]

Опции: -h, --help | --dry-run | --list-tasks

Примеры:
  ./scripts/remote/remote-run.sh board-orange ./scripts/remote/tasks/install-telemetry-client.sh
  ./scripts/remote/remote-run.sh orangepi 192.168.1.50 ./scripts/remote/tasks/telemetry-status.sh
EOF
}

list_tasks() {
  echo "Доступные задачи в ${REMOTE_TASKS_DIR}:"
  local f
  shopt -s nullglob
  for f in "${REMOTE_TASKS_DIR}"/*.sh; do
    echo "  ${f}"
  done
  shopt -u nullglob
}

source "${REMOTE_LIB_DIR}/remote-ssh.sh"

parse_cli() {
  local -a positional=()
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -h|--help) usage; exit 0 ;;
      --dry-run) REMOTE_DRY_RUN=1; shift ;;
      --list-tasks) LIST_TASKS=1; shift ;;
      --) shift; positional+=("$@"); break ;;
      -*) echo "Неизвестная опция: $1" >&2; exit 1 ;;
      *) positional+=("$1"); shift ;;
    esac
  done
  REMOTE_CLI_ARGS=("${positional[@]}")
}

find_task_file() {
  local -a args=("$@")
  local i arg
  TASK_FILE=""
  TARGET_ARGC=0
  TASK_ARGS=()
  for ((i = 0; i < ${#args[@]}; i++)); do
    arg="${args[i]}"
    if [[ -f "${arg}" ]]; then
      TASK_FILE="${arg}"
      TARGET_ARGC="${i}"
      if (( i + 1 < ${#args[@]} )); then
        TASK_ARGS=("${args[@]:i+1}")
      fi
      return 0
    fi
  done
  return 1
}

main() {
  parse_cli "$@"
  if [[ "${LIST_TASKS}" -eq 1 ]]; then
    list_tasks
    exit 0
  fi
  if ! find_task_file "${REMOTE_CLI_ARGS[@]}"; then
    echo "Ошибка: не найден task-file" >&2
    usage >&2
    exit 1
  fi
  if [[ "${TARGET_ARGC}" -lt 1 ]]; then
    echo "Ошибка: не указана цель SSH" >&2
    exit 1
  fi
  local -a target_args=("${REMOTE_CLI_ARGS[@]:0:TARGET_ARGC}")
  remote_parse_target "${target_args[@]}" || exit 1
  remote_init_transport
  export REMOTE_DRY_RUN REPO_ROOT REMOTE_ROOT REMOTE_TASKS_DIR
  source "${TASK_FILE}"
  # #region agent log
  printf '{"sessionId":"f1ee75","hypothesisId":"B","location":"remote-run.sh","message":"after source task and lib","data":{"has_remote_scp":%s,"has_remote_scp_in_lib":%s,"task_file":"%s"},"timestamp":%s}\n' \
    "$(declare -F remote_scp >/dev/null 2>&1 && echo true || echo false)" \
    "$(grep -c '^remote_scp()' "${REMOTE_LIB_DIR}/remote-ssh.sh" 2>/dev/null || echo 0)" \
    "${TASK_FILE}" "$(date +%s%3N)" \
    >> "/home/pyler/Projects/Infoteh/Infoteh-Main-Project/projects/CAN-Telemetry-API-Service/.cursor/debug-f1ee75.log" 2>/dev/null || true
  # #endregion
  if ! declare -F remote_task >/dev/null 2>&1; then
    echo "Ошибка: нет remote_task() в ${TASK_FILE}" >&2
    exit 1
  fi
  remote_print_info
  echo "    task: ${TASK_FILE}"
  echo
  remote_task "${TASK_ARGS[@]}"
}

main "$@"
