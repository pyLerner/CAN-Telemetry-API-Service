# telemetry-client

Автономный клиент для логирования **состояний дверей** с [CAN Telemetry API](../doc/API-TELEMETRY-V1.md).

## Назначение

Клиент с заданным интервалом опрашивает `GET /api/telemetry/v1/doors/state` и записывает в файл:

- при **смене** состояния двери;
- либо **все текущие** состояния при первом успешном опросе (`write-initial-state = true`);
- либо **синтетическое** `close` по истечении `timeout` для состояния `open`.

```text
[2026-05-22 14:30:01] [INFO] door 1 open
[2026-05-22 14:30:05] [INFO] door 2 close
```

Ошибки — в **stderr** (`journalctl` при systemd), не в door-log.

При каждом **запуске** программы файл лога **пересоздаётся** (старые записи не сохраняются).

## Требования

- Python **3.10+**, только stdlib
- CAN Telemetry API (по умолчанию `192.168.9.220:7080`)

## Конфигурация (INI)

Файл [`client.ini`](client.ini) в репозитории — рабочий шаблон; на плате: `/opt/telemetry-client/etc/client.ini`.

При каждом запуске `door_logger.py` **пересоздаёт** INI по пути `-c` (дефолты → старый файл → CLI).

Секция `[client]`:

| Ключ | По умолчанию | Описание |
|------|--------------|----------|
| `api-server-host` | `192.168.9.220` | хост API |
| `api-server-port` | `7080` | порт API |
| `log-path` | `/usr/local/Bus/Services/PasCounter/recv/recv.txt` | файл лога дверей |
| `last-state-only` | `true` | одна строка на дверь (обновление на месте) |
| `poll-interval-sec` | `0.3` | интервал опроса, сек |
| `write-unknown-state` | `false` | писать переходы с/на `unknown` |
| `write-initial-state` | `true` | записать все двери при первом опросе |
| `timeout` | `60` | авто-закрытие `open`, сек (`0` = выключено) |
| `timezone` | `local` | `utc`, `local` или IANA (`Europe/Moscow`) |

## CLI

| Параметр | Описание |
|----------|----------|
| `-h` / `--host` | хост API |
| `-p` / `--port` | порт API |
| `-c` / `--config` | путь к INI |
| `--interval` | интервал опроса, сек |
| `-i` / `--initial` | `true` / `false` — записать состояния при старте |
| `-u` / `--unknown` | `true` / `false` — логировать `unknown` |
| `-l` / `--last-state-only` | `true` / `false` — режим одной строки на дверь |
| `--timeout` | авто-закрытие `open`, сек (`0` = выключено) |
| `-t` / `--timezone` | `utc`, `local` или IANA-зона |
| `--help` | справка |

Приоритет: дефолты → существующий `-c` (до перезаписи) → CLI.

### `last-state-only`

- `true` (по умолчанию) — в файле всегда **N строк для N дверей**; при смене состояния обновляется только строка этой двери.
- `false` — каждое событие **дописывается** в конец файла.

При `write-initial-state = false` и `last-state-only = true` файл остаётся пустым до первого изменения каждой двери.

Если дверь **исчезла из ответа API** во время работы, строка в файле **не меняется** (остаётся последнее известное состояние).

### `write-initial-state`

- `false` — первый опрос только запоминает снимок, в файл пишутся **только изменения** (или пустой файл при `last-state-only = true`).
- `true` (по умолчанию) — при первом успешном опросе в лог попадает текущее состояние **каждой** двери (таймеры `open` **не** стартуют).

### `timeout` (авто-закрытие open)

- `0` — выключено, только реальные переходы от API.
- `N > 0` — после перехода **`close → open`** (по снимкам API) стартует таймер на `N` секунд.
- Если за это время API не прислал `close`, клиент пишет синтетическое `door N close`.
- Повторный API `close` после синтетического **не** пишется в лог.
- API `open` после синтетического **игнорируется** до реального API `close`.
- Повторные API `open` без смены состояния таймер **не** продлевают.
- API `unknown` во время открытой двери таймер **не** отменяет.

### `unknown`

При `write-unknown-state = false` в лог (после первого опроса) попадают только переходы `open` ↔ `close`.

При `true` дополнительно переходы с/на `unknown`.

### Часовой пояс

- `utc` — UTC
- `local` — системная зона хоста (`/etc/localtime`)
- иначе — IANA, например `Europe/Moscow`

## Установка

На плате из каталога `telemetry-client/`:

```bash
sudo ./install.sh
```

Копирует `door_logger.py` и `client.ini` → `/opt/telemetry-client/etc/client.ini`, создаёт каталог из `log-path`, назначает владельца **1000:1000**. Сервис systemd работает от **UID 1000**.

### Удалённая установка (SSH)

```bash
./telemetry-client/install-remote.sh orangepi <host> [port]
```

Порт SSH: **22**. Пути и адрес API — в начале [`install-remote.sh`](install-remote.sh).

При установке по SSH потребуется **пароль sudo** на плате (или настройте passwordless sudo для пользователя `orangepi`).

### Проверка

```bash
journalctl -u telemetry-client -f
tail -f /usr/local/Bus/Services/PasCounter/recv/recv.txt
curl -s http://192.168.9.220:7080/api/ping
```

### Остановка сервиса

```bash
sudo systemctl stop telemetry-client.service
```

## Ручной запуск

```bash
python3 door_logger.py -c ./client.ini
python3 door_logger.py -h 192.168.9.220 -p 7080 --interval 0.3 --timeout 60 -i true -l true -t local
```

## Файлы

| Файл | Назначение |
|------|------------|
| `door_logger.py` | программа-клиент |
| `client.ini` | рабочий конфиг (в git) |
| `client.ini.example` | справочная копия |
| `telemetry-client.service` | systemd unit (User=1000) |
| `install.sh` | установка в `/opt/telemetry-client` |
| `install-remote.sh` | установка по SSH |
