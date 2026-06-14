#!/usr/bin/env bash
# remote-task: telemetry-status

remote_task() {
  remote_echo "==> Статус telemetry-client.service"
  remote_ssh "systemctl --no-pager --full status telemetry-client.service || true"
}
