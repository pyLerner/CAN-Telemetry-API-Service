# Deploy bundle: `/opt/can-telemetry`

Каталог копируется на плату RK3568 в `/opt/can-telemetry/` и монтируется в контейнер (`docker-compose.yml`).

## Содержимое

| Путь | Назначение |
|------|------------|
| `etc/telemetry-provider.toml` | Конфиг сервиса (пути `/app`, `/app/logs`) |
| `logs/` | Логи на хосте → `/app/logs` в контейнере |
| `data/` | Файлы DBC при `Decoder = "dbc"` → `/app/data` |

## Установка на плату

Из корня клона репозитория:

```bash
sudo ./docker/can-telemetry/install-to-opt.sh
```

### Удалённая установка (SSH)

С рабочей станции (нужны `ssh`, `rsync`):

```bash
./docker/install-remote.sh teamhd <host> [port]
```

По умолчанию порт SSH: **22**. Пути на плате заданы в начале `docker/install-remote.sh` (`REMOTE_PROJECT_DIR`, `REMOTE_OPT_DIR`).

Или вручную:

```bash
sudo mkdir -p /opt/can-telemetry
sudo cp -a docker/can-telemetry/etc docker/can-telemetry/logs docker/can-telemetry/data /opt/can-telemetry/
sudo chown -R 1000:1000 /opt/can-telemetry
```

## Запуск Docker

1. Включён **`can0-setup.service`** (поднимает `can0` на хосте, 250 kbit/s, listen-only).
2. Собрать образ: `../build-rk3568.sh` из `docker/` или `./docker/build-rk3568.sh` из корня репо.
3. Запуск: `docker compose -f docker/docker-compose.yml up -d` из корня репо.
4. Отключить **`can-telemetry.service`** (systemd), если ранее использовался нативный запуск.

## Проверка

```bash
curl -s http://127.0.0.1:7080/api/ping
tail -f /opt/can-telemetry/logs/can-telemetry.log
```

## Обновление конфига

Правка `/opt/can-telemetry/etc/telemetry-provider.toml`, затем:

```bash
docker compose -f docker/docker-compose.yml restart
```

Пересборка образа не требуется.

## DBC-файлы

При переключении на `Decoder = "dbc"` или `bus-fms` положите `.dbc` в `/opt/can-telemetry/data/` и укажите в конфиге:

```toml
[Mapping]
dbc_path = "/app/data/your-bus.dbc"
```
