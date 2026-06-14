#!/usr/bin/env bash
# remote-task: apply-timesyncd
# Копирует timesyncd.conf на плату и настраивает systemd-timesyncd.

# #region agent log
_apply_timesyncd_debug_log() {
  local hypothesis_id="$1" message="$2" data="$3"
  printf '{"sessionId":"f1ee75","hypothesisId":"%s","location":"apply-timesyncd.sh","message":"%s","data":%s,"timestamp":%s}\n' \
    "${hypothesis_id}" "${message}" "${data}" "$(date +%s%3N)" \
    >> "/home/pyler/Projects/Infoteh/Infoteh-Main-Project/projects/CAN-Telemetry-API-Service/.cursor/debug-f1ee75.log" 2>/dev/null || true
}
# #endregion

remote_task() {
  # #region agent log
  _apply_timesyncd_debug_log "A" "remote_task entry" \
    "{\"has_remote_scp\":$(declare -F remote_scp >/dev/null 2>&1 && echo true || echo false),\"has_remote_echo\":$(declare -F remote_echo >/dev/null 2>&1 && echo true || echo false),\"bash_source0\":\"${BASH_SOURCE[0]:-}\",\"argv0\":\"${0:-}\"}"
  # #endregion

  local task_dir
  task_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  local local_config="${task_dir}/timesyncd.conf"
  local remote_tmp="/tmp/timesyncd.conf.tmp"

  if [[ ! -f "${local_config}" ]]; then
    echo "Ошибка: локальный файл не найден: ${local_config}" >&2
    return 1
  fi

  remote_echo "==> 1. Копирование ${local_config} на удалённый хост"
  remote_scp "${local_config}" "${remote_tmp}"

  remote_echo "==> 2. Применение конфигурации и перезапуск systemd-timesyncd"
  remote_sudo "mv '${remote_tmp}' /etc/systemd/timesyncd.conf && \
chown root:root /etc/systemd/timesyncd.conf && \
chmod 644 /etc/systemd/timesyncd.conf && \
timedatectl set-ntp true && \
systemctl restart systemd-timesyncd"

  remote_echo "==> 3. Статус синхронизации времени"
  remote_sudo "timedatectl status"

  remote_echo "Готово."
}
