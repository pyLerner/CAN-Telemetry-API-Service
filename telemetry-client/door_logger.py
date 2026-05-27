#!/usr/bin/env python3
"""
Клиент логирования состояний дверей CAN Telemetry API.

Назначение
----------
Периодически опрашивает REST API сервиса телеметрии и дописывает в файл
только те события, когда состояние двери **изменилось** (open / close / unknown).

Требования: Python 3.10+, только стандартная библиотека.

Поведение логов
---------------
* Файл door-log — только строки вида ``[YYYY-MM-DD HH:MM:SS] [INFO] door N <state>``.
* Ошибки HTTP, сеть, парсинг JSON — в stderr (при systemd: ``journalctl``).
* Первый опрос: по умолчанию только запоминает снимок; при ``write-initial-state = true``
  записывает текущие состояния всех дверей в файл.

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
DEFAULT_TIMEZONE = "utc"
HTTP_TIMEOUT_SEC = 5.0

# Допустимые состояния согласно doc/API-TELEMETRY-V1.md
VALID_STATES = frozenset({"open", "close", "unknown"})

# Логгер для служебных сообщений (stderr), не для door-log файла
logger = logging.getLogger("telemetry-client")


def _stderr_handler() -> None:
    """
    Настроить вывод служебных сообщений только в stderr.

    Door-log пишется отдельно в файл; сюда попадают ошибки опроса,
    старт/остановка и предупреждения о некорректных состояниях API.
    """
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)


def _parse_bool(value: str | None, default: bool) -> bool:
    """
    Разобрать булево значение из строки INI или CLI.

    Parameters
    ----------
    value:
        Строка из конфига/аргумента. ``None`` — вернуть ``default``.
    default:
        Значение, если ``value`` не задан.

    Returns
    -------
    bool
        Распознанное логическое значение.

    Raises
    ------
    ValueError
        Если строка не похожа на true/false.
    """
    if value is None:
        return default
    normalized = str(value).strip().lower()
    if normalized in ("1", "true", "yes", "on"):
        return True
    if normalized in ("0", "false", "no", "off"):
        return False
    raise ValueError(f"invalid boolean value: {value!r}")


def _load_existing_config(path: Path) -> dict[str, str]:
    """
    Прочитать существующий INI до его перезаписи при старте.

    Parameters
    ----------
    path:
        Путь к ``client.ini``.

    Returns
    -------
    dict[str, str]
        Пары ключ/значение из секции ``[client]`` или пустой словарь.
    """
    if not path.is_file():
        return {}
    parser = configparser.ConfigParser()
    parser.read(path, encoding="utf-8")
    if not parser.has_section("client"):
        return {}
    return dict(parser.items("client"))


def _write_config(path: Path, values: dict[str, str]) -> None:
    """
    Записать актуальный INI-конфиг (пересоздание файла при каждом запуске).

    Parameters
    ----------
    path:
        Целевой путь к конфигу.
    values:
        Итоговые параметры секции ``[client]``.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    parser = configparser.ConfigParser()
    parser["client"] = values
    with path.open("w", encoding="utf-8") as fh:
        parser.write(fh)


def resolve_timezone(name: str) -> timezone | ZoneInfo:
    """
    Получить объект часового пояса для меток времени в door-log.

    Parameters
    ----------
    name:
        * ``utc`` — UTC;
        * ``local`` — системная зона хоста (``/etc/localtime``);
        * иначе — имя зоны IANA, например ``Europe/Moscow``.

    Returns
    -------
    timezone | ZoneInfo
        Объект для ``datetime.now(tz)``.
    """
    normalized = name.strip().lower()
    if normalized == "utc":
        return timezone.utc
    if normalized == "local":
        # Пытаемся взять зону из текущего локального времени ОС
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
    """
    Собрать итоговые настройки и перезаписать INI на диске.

    Алгоритм приоритета (по ТЗ):
    1. Встроенные константы модуля.
    2. Существующий файл по ``-c``, если он есть.
    3. Явные аргументы командной строки.

    Parameters
    ----------
    args:
        Результат :func:`parse_args`.

    Returns
    -------
    dict[str, Any]
        Словарь с ключами ``host``, ``port``, ``log_path``,
        ``poll_interval_sec``, ``write_unknown``, ``write_initial``,
        ``timezone``, ``config_path``.
    """
    config_path = Path(args.config) if args.config else DEFAULT_CONFIG_PATH

    settings: dict[str, str] = {
        "api-server-host": DEFAULT_HOST,
        "api-server-port": str(DEFAULT_PORT),
        "log-path": DEFAULT_LOG_PATH,
        "poll-interval-sec": str(DEFAULT_POLL_INTERVAL_SEC),
        "write-unknown-state": "false" if not DEFAULT_WRITE_UNKNOWN else "true",
        "write-initial-state": "false" if not DEFAULT_WRITE_INITIAL else "true",
        "timezone": DEFAULT_TIMEZONE,
    }

    existing = _load_existing_config(config_path)
    for key in settings:
        if key in existing:
            settings[key] = existing[key]

    # CLI перекрывает всё, что передано явно
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

    _write_config(config_path, settings)

    write_unknown = _parse_bool(settings["write-unknown-state"], DEFAULT_WRITE_UNKNOWN)
    write_initial = _parse_bool(settings["write-initial-state"], DEFAULT_WRITE_INITIAL)
    tz = resolve_timezone(settings["timezone"])

    return {
        "config_path": config_path,
        "host": settings["api-server-host"],
        "port": int(settings["api-server-port"]),
        "log_path": Path(settings["log-path"]),
        "poll_interval_sec": float(settings["poll-interval-sec"]),
        "write_unknown": write_unknown,
        "write_initial": write_initial,
        "timezone": tz,
    }


def fetch_doors(host: str, port: int) -> dict[str, str]:
    """
    Запросить текущие состояния всех дверей у API.

    Endpoint: ``GET /api/telemetry/v1/doors/state``.

    Parameters
    ----------
    host:
        Хост сервера телеметрии.
    port:
        Порт HTTP (по умолчанию 7080).

    Returns
    -------
    dict[str, str]
        Номер двери (строка) → нормализованное состояние
        (``open``, ``close`` или ``unknown``).

    Raises
    ------
    urllib.error.URLError
        Сеть или HTTP-ошибка.
    ValueError
        Некорректный JSON или отсутствует объект ``doors``.
    json.JSONDecodeError
        Тело ответа не JSON.
    """
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
    """
    Решить, нужно ли записать строку в door-log при смене состояния.

    Parameters
    ----------
    old:
        Предыдущее состояние двери или ``None`` (ещё не было снимка).
    new:
        Новое состояние после опроса.
    write_unknown:
        Если ``False`` — логируются только переходы между ``open`` и ``close``.
        Если ``True`` — дополнительно переходы с/на ``unknown``.

    Returns
    -------
    bool
        ``True``, если событие следует записать в файл.
    """
    if old is None:
        return False
    if old == new:
        return False
    # open <-> close — всегда в лог
    if old in ("open", "close") and new in ("open", "close"):
        return True
    if not write_unknown:
        return False
    # unknown учитывается только при write-unknown-state = true
    if old in ("open", "close") and new == "unknown":
        return True
    if old == "unknown" and new in ("open", "close"):
        return True
    return False


def format_door_line(door_id: str, state: str, tz: timezone | ZoneInfo) -> str:
    """
    Сформировать одну строку door-log в требуемом формате.

    Parameters
    ----------
    door_id:
        Номер двери (как в API, обычно ``"1"`` … ``"6"``).
    state:
        Состояние: ``open``, ``close`` или ``unknown``.
    tz:
        Часовой пояс для метки времени.

    Returns
    -------
    str
        Строка с переводом строки в конце, готовая к записи в файл.
    """
    ts = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
    return f"[{ts}] [INFO] door {door_id} {state}\n"


def write_initial_states(
    current: dict[str, str],
    log_path: Path,
    tz: timezone | ZoneInfo,
) -> None:
    """
    Записать в door-log текущие состояния всех дверей (первый опрос при старте).

    Parameters
    ----------
    current:
        Снимок ``{door_id: state}`` с API.
    log_path:
        Путь к файлу лога.
    tz:
        Часовой пояс меток времени.
    """
    if not current:
        return
    lines: list[str] = []
    for door_id in sorted(current, key=lambda x: int(x) if x.isdigit() else x):
        lines.append(format_door_line(door_id, current[door_id], tz))
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as fh:
        fh.writelines(lines)
        fh.flush()


def process_changes(
    last: dict[str, str] | None,
    current: dict[str, str],
    log_path: Path,
    tz: timezone | ZoneInfo,
    *,
    write_unknown: bool,
    seed_only: bool,
) -> dict[str, str]:
    """
    Сравнить снимки дверей и дописать изменения в файл.

    Parameters
    ----------
    last:
        Предыдущий снимок ``{door_id: state}`` или ``None``.
    current:
        Текущий снимок с API.
    log_path:
        Путь к door-log файлу.
    tz:
        Часовой пояс меток времени.
    write_unknown:
        Учитывать ли переходы через ``unknown`` (см. :func:`should_log_transition`).
    seed_only:
        Если ``True`` — только запомнить ``current``, в файл не писать
        (первый успешный опрос после старта).

    Returns
    -------
    dict[str, str]
        Копия ``current`` для использования как ``last`` на следующей итерации.
    """
    if seed_only or last is None:
        return dict(current)

    lines: list[str] = []
    # Объединяем ключи: в ответе API могут появиться/исчезнуть номера дверей
    all_ids = sorted(set(last) | set(current), key=lambda x: int(x) if x.isdigit() else x)
    for door_id in all_ids:
        old = last.get(door_id)
        new = current.get(door_id, "unknown")
        if should_log_transition(old, new, write_unknown=write_unknown):
            lines.append(format_door_line(door_id, new, tz))

    if lines:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.writelines(lines)
            fh.flush()

    return dict(current)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """
    Разобрать аргументы командной строки.

    Parameters
    ----------
    argv:
        Список аргументов без имени программы; ``None`` — ``sys.argv[1:]``.

    Returns
    -------
    argparse.Namespace
        ``host``, ``port``, ``config``, ``interval``, ``initial``, ``unknown``, ``timezone``.
    """

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
        "--timezone",
        "-t",
        dest="timezone",
        default=None,
        help='часовой пояс: utc, local или IANA, напр. Europe/Moscow',
    )
    return parser.parse_args(argv)


def run_loop(settings: dict[str, Any]) -> int:
    """
    Основной цикл опроса API до прерывания (Ctrl+C).

    Parameters
    ----------
    settings:
        Результат :func:`resolve_settings`.

    Returns
    -------
    int
        Код выхода: ``0`` при штатной остановке, ``1`` при ошибке конфигурации.
    """
    host = settings["host"]
    port = settings["port"]
    log_path: Path = settings["log_path"]
    interval: float = settings["poll_interval_sec"]
    write_unknown: bool = settings["write_unknown"]
    write_initial: bool = settings["write_initial"]
    tz = settings["timezone"]

    if interval <= 0:
        logger.error("poll-interval-sec must be positive, got %s", interval)
        return 1

    logger.info(
        "starting door logger: %s:%s interval=%ss log=%s "
        "write_unknown=%s write_initial=%s timezone=%s",
        host,
        port,
        interval,
        log_path,
        write_unknown,
        write_initial,
        tz,
    )

    last: dict[str, str] | None = None
    first_poll = True

    while True:
        try:
            current = fetch_doors(host, port)
            if first_poll and write_initial:
                write_initial_states(current, log_path, tz)
                last = dict(current)
            else:
                last = process_changes(
                    last,
                    current,
                    log_path,
                    tz,
                    write_unknown=write_unknown,
                    seed_only=first_poll,
                )
            first_poll = False
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
    """
    Точка входа: настройка логирования, конфиг, запуск цикла опроса.

    Parameters
    ----------
    argv:
        Аргументы командной строки; ``None`` — из ``sys.argv``.

    Returns
    -------
    int
        Код возврата для ``sys.exit``.
    """
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
