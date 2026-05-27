#!/usr/bin/env python3
"""
Клиент логирования состояний дверей CAN Telemetry API.

Назначение
----------
Периодически опрашивает REST API сервиса телеметрии и дописывает в файл
события при **изменении** состояния двери (open / close / unknown).

Дополнительно поддерживается **timeout** для ``open``: если за заданное время
от API не пришёл ``close``, клиент сам пишет синтетическое ``door N close``.

Требования: Python 3.10+, только стандартная библиотека.

Поведение логов
---------------
* Файл door-log — строки вида ``[YYYY-MM-DD HH:MM:SS] [INFO] door N <state>``.
* Ошибки HTTP, сеть, парсинг JSON — в stderr (при systemd: ``journalctl``).
* Первый опрос: по умолчанию только запоминает снимок; при ``write-initial-state = true``
  записывает текущие состояния всех дверей в файл (таймеры open не стартуют).

Конфигурация
------------
INI-файл пересоздаётся при каждом запуске. Приоритет значений:
встроенные дефолты → существующий файл ``-c`` (до перезаписи) → аргументы CLI.
"""

from __future__ import annotations

import argparse
import configparser
import json
import logging
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

# --- Пути и значения по умолчанию (совпадают с install.sh / systemd unit) ---

DEFAULT_CONFIG_PATH = Path("/opt/telemetry-client/etc/client.ini")
DEFAULT_HOST = "192.168.9.220"
DEFAULT_PORT = 7080
DEFAULT_LOG_PATH = "/opt/telemetry-client/logs/doors.log"
DEFAULT_POLL_INTERVAL_SEC = 1.0
DEFAULT_WRITE_UNKNOWN = False
DEFAULT_WRITE_INITIAL = False
DEFAULT_OPEN_TIMEOUT_SEC = 0
DEFAULT_TIMEZONE = "utc"
HTTP_TIMEOUT_SEC = 5.0

# Допустимые состояния согласно doc/API-TELEMETRY-V1.md
VALID_STATES = frozenset({"open", "close", "unknown"})

# Логгер для служебных сообщений (stderr), не для door-log файла
logger = logging.getLogger("telemetry-client")


@dataclass
class DoorState:
    """
    Состояние одной двери с точки зрения клиента.

    effective
        Текущее состояние для логики логирования (может отличаться от API
        после синтетического ``close`` по timeout).
    api_last
        Предыдущий снимок API (для детекта ``close → open``).
    open_deadline
        Момент ``time.monotonic()``, когда истечёт таймер open; ``None`` если выключен.
    awaiting_real_close
        После синтетического ``close`` игнорируем API ``open`` до реального ``close``.
    """

    effective: str
    api_last: str | None
    open_deadline: float | None = None
    awaiting_real_close: bool = False


def _stderr_handler() -> None:
    """Настроить вывод служебных сообщений только в stderr."""
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)


def _parse_bool(value: str | None, default: bool) -> bool:
    """Разобрать булево значение из строки INI или CLI."""
    if value is None:
        return default
    normalized = str(value).strip().lower()
    if normalized in ("1", "true", "yes", "on"):
        return True
    if normalized in ("0", "false", "no", "off"):
        return False
    raise ValueError(f"invalid boolean value: {value!r}")


def _door_sort_key(door_id: str) -> tuple[int, str]:
    return (int(door_id), door_id) if door_id.isdigit() else (10**9, door_id)


def _load_existing_config(path: Path) -> dict[str, str]:
    """Прочитать существующий INI до его перезаписи при старте."""
    if not path.is_file():
        return {}
    parser = configparser.ConfigParser()
    parser.read(path, encoding="utf-8")
    if not parser.has_section("client"):
        return {}
    return dict(parser.items("client"))


def _write_config(path: Path, values: dict[str, str]) -> None:
    """Записать актуальный INI-конфиг (пересоздание файла при каждом запуске)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    parser = configparser.ConfigParser()
    parser["client"] = values
    with path.open("w", encoding="utf-8") as fh:
        parser.write(fh)


def resolve_timezone(name: str) -> timezone | ZoneInfo:
    """Получить объект часового пояса для меток времени в door-log."""
    normalized = name.strip().lower()
    if normalized == "utc":
        return timezone.utc
    if normalized == "local":
        try:
            tz_key = datetime.now().astimezone().tzinfo
            if isinstance(tz_key, ZoneInfo):
                return tz_key
            if tz_key is not None and hasattr(tz_key, "key"):
                return ZoneInfo(tz_key.key)  # type: ignore[attr-defined]
        except Exception:
            pass
        try:
            import time as time_mod

            if time_mod.tzname[0]:
                return ZoneInfo(time_mod.tzname[0])
        except Exception:
            pass
        return datetime.now().astimezone().tzinfo or timezone.utc
    return ZoneInfo(name)


def resolve_settings(args: argparse.Namespace) -> dict[str, Any]:
    """Собрать итоговые настройки и перезаписать INI на диске."""
    config_path = Path(args.config) if args.config else DEFAULT_CONFIG_PATH

    settings: dict[str, str] = {
        "api-server-host": DEFAULT_HOST,
        "api-server-port": str(DEFAULT_PORT),
        "log-path": DEFAULT_LOG_PATH,
        "poll-interval-sec": str(DEFAULT_POLL_INTERVAL_SEC),
        "write-unknown-state": "false" if not DEFAULT_WRITE_UNKNOWN else "true",
        "write-initial-state": "false" if not DEFAULT_WRITE_INITIAL else "true",
        "timeout": str(DEFAULT_OPEN_TIMEOUT_SEC),
        "timezone": DEFAULT_TIMEZONE,
    }

    existing = _load_existing_config(config_path)
    for key in settings:
        if key in existing:
            settings[key] = existing[key]

    if args.host is not None:
        settings["api-server-host"] = args.host
    if args.port is not None:
        settings["api-server-port"] = str(args.port)
    if args.interval is not None:
        settings["poll-interval-sec"] = str(args.interval)
    if args.unknown is not None:
        settings["write-unknown-state"] = "true" if args.unknown else "false"
    if args.timezone is not None:
        settings["timezone"] = args.timezone
    if args.initial is not None:
        settings["write-initial-state"] = "true" if args.initial else "false"
    if args.timeout is not None:
        settings["timeout"] = str(args.timeout)

    _write_config(config_path, settings)

    open_timeout_sec = int(settings["timeout"])
    if open_timeout_sec < 0:
        raise ValueError(f"timeout must be >= 0, got {open_timeout_sec}")

    return {
        "config_path": config_path,
        "host": settings["api-server-host"],
        "port": int(settings["api-server-port"]),
        "log_path": Path(settings["log-path"]),
        "poll_interval_sec": float(settings["poll-interval-sec"]),
        "write_unknown": _parse_bool(settings["write-unknown-state"], DEFAULT_WRITE_UNKNOWN),
        "write_initial": _parse_bool(settings["write-initial-state"], DEFAULT_WRITE_INITIAL),
        "open_timeout_sec": open_timeout_sec,
        "timezone": resolve_timezone(settings["timezone"]),
    }


def fetch_doors(host: str, port: int) -> dict[str, str]:
    """Запросить текущие состояния всех дверей у API."""
    url = f"http://{host}:{port}/api/telemetry/v1/doors/state"
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SEC) as resp:
        body = resp.read().decode("utf-8")
    data = json.loads(body)
    doors = data.get("doors")
    if not isinstance(doors, dict):
        raise ValueError("invalid response: missing or invalid 'doors' object")
    result: dict[str, str] = {}
    for door_id, state in doors.items():
        state_s = str(state).lower()
        if state_s not in VALID_STATES:
            logger.warning("door %s: unexpected state %r, treating as unknown", door_id, state)
            state_s = "unknown"
        result[str(door_id)] = state_s
    return result


def should_log_transition(
    old: str | None,
    new: str,
    *,
    write_unknown: bool,
) -> bool:
    """Решить, нужно ли записать строку в door-log при смене состояния."""
    if old is None:
        return False
    if old == new:
        return False
    if old in ("open", "close") and new in ("open", "close"):
        return True
    if not write_unknown:
        return False
    if old in ("open", "close") and new == "unknown":
        return True
    if old == "unknown" and new in ("open", "close"):
        return True
    return False


def format_door_line(door_id: str, state: str, tz: timezone | ZoneInfo) -> str:
    """Сформировать одну строку door-log в требуемом формате."""
    ts = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
    return f"[{ts}] [INFO] door {door_id} {state}\n"


def append_door_lines(lines: list[str], log_path: Path) -> None:
    """Дописать строки door-log в файл."""
    if not lines:
        return
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as fh:
        fh.writelines(lines)
        fh.flush()


def write_initial_states(
    current: dict[str, str],
    log_path: Path,
    tz: timezone | ZoneInfo,
) -> None:
    """Записать текущие состояния всех дверей (первый опрос при write-initial-state)."""
    if not current:
        return
    lines = [
        format_door_line(door_id, current[door_id], tz)
        for door_id in sorted(current, key=_door_sort_key)
    ]
    append_door_lines(lines, log_path)


def init_door_states(current: dict[str, str]) -> dict[str, DoorState]:
    """Инициализировать состояния дверей из первого снимка API (без таймеров)."""
    return {
        door_id: DoorState(effective=state, api_last=state)
        for door_id, state in current.items()
    }


def check_open_timeouts(
    doors: dict[str, DoorState],
    log_path: Path,
    tz: timezone | ZoneInfo,
) -> None:
    """
    Синтетическое закрытие дверей по истечении open-таймера.

    Срабатывает, если ``open_deadline`` задан и текущее monotonic-время
    его превысило. ``unknown`` от API таймер не отменяет.
    """
    now = time.monotonic()
    lines: list[str] = []
    for door_id in sorted(doors, key=_door_sort_key):
        state = doors[door_id]
        if state.open_deadline is None or now < state.open_deadline:
            continue
        lines.append(format_door_line(door_id, "close", tz))
        state.effective = "close"
        state.open_deadline = None
        state.awaiting_real_close = True
    append_door_lines(lines, log_path)


def apply_api_snapshot(
    doors: dict[str, DoorState],
    current: dict[str, str],
    log_path: Path,
    tz: timezone | ZoneInfo,
    *,
    write_unknown: bool,
    open_timeout_sec: int,
) -> None:
    """
    Обработать новый снимок API с учётом timeout и awaiting_real_close.

    Таймер open стартует только при ``api_last == close`` и API ``open``.
    """
    lines: list[str] = []
    all_ids = sorted(set(doors) | set(current), key=_door_sort_key)

    for door_id in all_ids:
        api_state = current.get(door_id, "unknown")
        if door_id not in doors:
            doors[door_id] = DoorState(effective=api_state, api_last=None)

        state = doors[door_id]
        api_prev = state.api_last

        if state.awaiting_real_close:
            if api_state == "close":
                state.awaiting_real_close = False
            state.api_last = api_state
            continue

        logged = False

        if api_prev == "close" and api_state == "open":
            lines.append(format_door_line(door_id, "open", tz))
            state.effective = "open"
            if open_timeout_sec > 0:
                state.open_deadline = time.monotonic() + open_timeout_sec
            logged = True
        elif state.effective == "open" and api_state == "close":
            lines.append(format_door_line(door_id, "close", tz))
            state.effective = "close"
            state.open_deadline = None
            logged = True
        elif should_log_transition(state.effective, api_state, write_unknown=write_unknown):
            lines.append(format_door_line(door_id, api_state, tz))
            state.effective = api_state
            if api_state == "close":
                state.open_deadline = None
            logged = True

        if not logged and api_state == "open" and state.effective == "open":
            pass

        state.api_last = api_state

    append_door_lines(lines, log_path)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Разобрать аргументы командной строки."""

    def _optional_bool(value: str) -> bool:
        return _parse_bool(value, False)

    parser = argparse.ArgumentParser(
        description="Логирование изменений состояний дверей (CAN Telemetry API)",
        add_help=False,
    )
    parser.add_argument("--help", action="help", help="показать справку и выйти")
    parser.add_argument("-h", "--host", dest="host", default=None, help="хост API")
    parser.add_argument("--port", "-p", dest="port", type=int, default=None, help="порт API")
    parser.add_argument(
        "--config",
        "-c",
        dest="config",
        default=None,
        help=f"путь к INI (по умолчанию: {DEFAULT_CONFIG_PATH})",
    )
    parser.add_argument(
        "--interval",
        dest="interval",
        type=float,
        default=None,
        help="интервал опроса, секунды",
    )
    parser.add_argument(
        "--initial",
        "-i",
        dest="initial",
        nargs="?",
        const=True,
        default=None,
        type=_optional_bool,
        metavar="BOOL",
        help="записать текущие состояния при старте: -i true / -i false (по умолчанию false)",
    )
    parser.add_argument(
        "--unknown",
        "-u",
        dest="unknown",
        nargs="?",
        const=True,
        default=None,
        type=_optional_bool,
        metavar="BOOL",
        help="логировать unknown: -u true / -u false (по умолчанию false)",
    )
    parser.add_argument(
        "--timeout",
        dest="timeout",
        type=int,
        default=None,
        help="авто-закрытие open, сек (0 = выключено, по умолчанию 0)",
    )
    parser.add_argument(
        "--timezone",
        "-t",
        dest="timezone",
        default=None,
        help="часовой пояс: utc, local или IANA, напр. Europe/Moscow",
    )
    return parser.parse_args(argv)


def run_loop(settings: dict[str, Any]) -> int:
    """Основной цикл опроса API до прерывания (Ctrl+C)."""
    host = settings["host"]
    port = settings["port"]
    log_path: Path = settings["log_path"]
    interval: float = settings["poll_interval_sec"]
    write_unknown: bool = settings["write_unknown"]
    write_initial: bool = settings["write_initial"]
    open_timeout_sec: int = settings["open_timeout_sec"]
    tz = settings["timezone"]

    if interval <= 0:
        logger.error("poll-interval-sec must be positive, got %s", interval)
        return 1

    logger.info(
        "starting door logger: %s:%s interval=%ss log=%s "
        "write_unknown=%s write_initial=%s open_timeout=%ss timezone=%s",
        host,
        port,
        interval,
        log_path,
        write_unknown,
        write_initial,
        open_timeout_sec,
        tz,
    )

    doors: dict[str, DoorState] | None = None
    first_poll = True

    while True:
        try:
            if doors is not None and open_timeout_sec > 0:
                check_open_timeouts(doors, log_path, tz)

            current = fetch_doors(host, port)
            if first_poll:
                if write_initial:
                    write_initial_states(current, log_path, tz)
                doors = init_door_states(current)
                first_poll = False
            else:
                apply_api_snapshot(
                    doors,
                    current,
                    log_path,
                    tz,
                    write_unknown=write_unknown,
                    open_timeout_sec=open_timeout_sec,
                )
        except urllib.error.URLError as exc:
            logger.error("HTTP request failed: %s", exc)
        except (json.JSONDecodeError, ValueError, OSError) as exc:
            logger.error("poll failed: %s", exc)

        try:
            time.sleep(interval)
        except KeyboardInterrupt:
            logger.info("stopped by user")
            return 0


def main(argv: list[str] | None = None) -> int:
    """Точка входа: настройка логирования, конфиг, запуск цикла опроса."""
    _stderr_handler()
    args = parse_args(argv)
    try:
        settings = resolve_settings(args)
    except (ValueError, configparser.Error) as exc:
        logger.error("config error: %s", exc)
        return 1
    logger.info("config written to %s", settings["config_path"])
    return run_loop(settings)


if __name__ == "__main__":
    sys.exit(main())
