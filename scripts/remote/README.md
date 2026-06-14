# scripts/remote — удалённое выполнение задач по SSH

Универсальный инструмент: **одинаковый разбор цели SSH** (как в `telemetry-client/install-remote.sh`) и **тело задачи** в отдельном файле.

## Быстрый старт

```bash
# Host из ~/.ssh/config
./scripts/remote/remote-run.sh board-orange ./scripts/remote/tasks/install-telemetry-client.sh

# Явные user / host / port
./scripts/remote/remote-run.sh orangepi 192.168.1.50 ./scripts/remote/tasks/telemetry-status.sh

# Список задач
./scripts/remote/remote-run.sh --list-tasks

# Без выполнения
./scripts/remote/remote-run.sh --dry-run board-orange ./scripts/remote/tasks/install-telemetry-client.sh
```

Каталог `telemetry-client/` не изменяется: по-прежнему можно использовать `telemetry-client/install-remote.sh`. Эквивалент через remote-run:

```bash
./scripts/remote/remote-run.sh <target> ./scripts/remote/tasks/install-telemetry-client.sh
```

## Структура

| Путь | Назначение |
|------|------------|
| `lib/remote-ssh.sh` | Библиотека: parse target, ssh, rsync, sudo |
| `remote-run.sh` | Диспетчер: цель + путь к task-файлу |
| `tasks/*.sh` | Задачи с функцией `remote_task()` |

## Цель SSH (target)

- **1 аргумент** — имя `Host` в `~/.ssh/config` (параметры из `ssh -G`).
- **2–3 аргумента** — `<user> <host> [port]`.

Staging по умолчанию: `/home/<user>/telemetry-client` (подкаталог задаётся `REMOTE_STAGING_SUBDIR`).

## Task-файл

Локальный bash-скрипт, подключаемый через `source`. Обязательна функция:

```bash
remote_task() {
  # аргументы после task-file в "$@"
  remote_ssh "команда"
  remote_sudo "команда"
  remote_rsync "${REPO_ROOT}/src/" "${RSYNC_DEST}"
}
```

Доступны переменные: `REPO_ROOT`, `REMOTE_USER`, `REMOTE_HOST`, `REMOTE_PORT`, `REMOTE_STAGING_DIR`, `RSYNC_DEST`, `USE_SSH_CONFIG`, `SSH_TARGET`.

## Переменные окружения

| Переменная | Описание |
|------------|----------|
| `SSH_OPTS` | Доп. опции ssh (`-i ключ` и т.д.) |
| `REMOTE_STAGING_SUBDIR` | Имя каталога под `/home/<user>/` (по умолчанию `telemetry-client`) |

## Задачи в `tasks/`

| Файл | Описание |
|------|----------|
| `install-telemetry-client.sh` | Установка telemetry-client |
| `telemetry-status.sh` | Статус сервиса telemetry-client |
| `apply-timesyncd.sh` | Деплой `timesyncd.conf` и настройка NTP (`timesyncd.conf` рядом с task) |

Пример timesyncd:

```bash
./scripts/remote/remote-run.sh board-orange ./scripts/remote/tasks/apply-timesyncd.sh
```

## Новая задача

1. Создать `tasks/my-task.sh` с `remote_task()`.
2. Запустить: `./scripts/remote/remote-run.sh <target> ./scripts/remote/tasks/my-task.sh`.
