from __future__ import annotations

import logging
from collections import deque
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from telemetry.cache import TelemetryCache

log = logging.getLogger("can-telemetry.t856")


class T856Decoder:
    """
    T856 decoder (doc/Согласование_телеметрии_Т856_Нижний_Новгород_v1_2026_03_10.pdf):
    - 0x18FF6227 Temperatures1
    - 0x18FF6427 IO (reverse)
    - 0x18FF6527 Doors (§2.6): per door 2-bit opening / closed / closing fields.
      Validated against field logs debug/20260521/.
    - API: close when «закрыта» active; opening/closing active => open; else open.
    """

    _ID_TEMPERATURES1 = 0x18FF6227
    _ID_IO = 0x18FF6427
    _ID_DOORS = 0x18FF6527

    def __init__(self) -> None:
        self._debug = False
        self._queue_len = 5
        self._average_all_zone = True
        self._sensor_selection: list[int] = [1, 2]
        self._reverse_code = 124
        self._inside_queues: dict[int, deque[float]] = {}
        self._outside_queue: deque[float] = deque(maxlen=5)
        self._id_match_mode = "arbitration-id"
        self._temperature_ids: set[int] = {self._ID_TEMPERATURES1}
        self._io_ids: set[int] = {self._ID_IO}
        self._door_ids: set[int] = {self._ID_DOORS}
        self._door_count = 4
        self._door_unknown_state = "unknown"

    def configure(self, mapping: dict[str, Any]) -> None:
        temp_cfg = _as_dict(mapping.get("temperature"))
        door_cfg = _as_dict(mapping.get("doors"))
        ids_cfg = _as_dict(mapping.get("ids"))
        reverse_cfg = _as_dict(mapping.get("reverse"))
        system_cfg = _as_dict(mapping.get("_system"))

        self._debug = bool(system_cfg.get("debug", False))

        self._queue_len = max(1, int(_to_number(temp_cfg.get("queue-len"), 5)))
        self._average_all_zone = bool(temp_cfg.get("average-all-zone", True))
        self._sensor_selection = _parse_sensors(temp_cfg.get("sensors", "all"))
        if not self._sensor_selection:
            self._sensor_selection = [1, 2]

        if not self._average_all_zone and len(self._sensor_selection) > 1:
            log.error(
                "Invalid config: average-all-zone=false with sensors=%s. "
                "Forcing average-all-zone=true.",
                self._sensor_selection,
            )
            self._average_all_zone = True

        self._inside_queues = {
            sid: deque(maxlen=self._queue_len) for sid in self._sensor_selection
        }
        self._outside_queue = deque(maxlen=self._queue_len)
        self._reverse_code = int(_to_number(reverse_cfg.get("reverse-code"), 124))
        cache_cfg = _as_dict(mapping.get("_cache"))
        self._door_count = max(1, int(_to_number(cache_cfg.get("door-count"), 4)))
        self._door_unknown_state = str(door_cfg.get("unknown-state", "unknown")).strip()
        if self._door_unknown_state not in ("unknown", "open", "close"):
            self._door_unknown_state = "unknown"
        match_mode = str(ids_cfg.get("match-mode", "arbitration-id")).strip().lower()
        if match_mode in ("arbitration-id", "pgn"):
            self._id_match_mode = match_mode
        else:
            self._id_match_mode = "arbitration-id"

        self._temperature_ids = _parse_id_set(
            ids_cfg.get("temperatures1"), self._ID_TEMPERATURES1
        )
        self._io_ids = _parse_id_set(ids_cfg.get("io"), self._ID_IO)
        self._door_ids = _parse_id_set(ids_cfg.get("doors"), self._ID_DOORS)
        if self._debug:
            log.debug(
                "T856 ID mapping configured: mode=%s doors=%s io=%s temperatures1=%s "
                "door_count=%s unknown=%s",
                self._id_match_mode,
                sorted(hex(i) for i in self._door_ids),
                sorted(hex(i) for i in self._io_ids),
                sorted(hex(i) for i in self._temperature_ids),
                self._door_count,
                self._door_unknown_state,
            )

    def decode_frame(self, msg: Any, cache: TelemetryCache) -> None:
        arb = int(msg.arbitration_id)
        data = bytes(msg.data)
        if self._matches_id(arb, self._temperature_ids):
            self._decode_temperatures1(data, cache)
            return
        if self._matches_id(arb, self._io_ids):
            self._decode_io(data, cache)
            return
        if self._matches_id(arb, self._door_ids):
            self._decode_doors(data, cache)

    def _matches_id(self, arbitration_id: int, allowed: set[int]) -> bool:
        if self._id_match_mode == "pgn":
            pgn = _j1939_pgn(arbitration_id)
            return pgn in allowed
        return arbitration_id in allowed

    def _decode_temperatures1(self, data: bytes, cache: TelemetryCache) -> None:
        if len(data) < 6:
            return
        sensor_raw = {
            1: float(int(data[1]) - 40),
            2: float(int(data[2]) - 40),
        }
        for sid, val in sensor_raw.items():
            q = self._inside_queues.get(sid)
            if q is not None:
                q.append(val)

        outside_raw = int.from_bytes(data[4:6], byteorder="little", signed=False)
        outside = float(outside_raw) * 0.03125 - 273.0
        self._outside_queue.append(outside)

        inside_avg = self._compute_inside_average()
        outside_avg = _avg(self._outside_queue)
        if inside_avg is not None:
            cache.set_temperature("inside", inside_avg)
        if outside_avg is not None:
            cache.set_temperature("outside", outside_avg)

        if self._debug:
            log.debug(
                "T856 Temperatures1 raw-computed values before normalization: "
                "inside=%s outside=%s sensors=%s",
                inside_avg,
                outside_avg,
                sensor_raw,
            )

    def _decode_io(self, data: bytes, cache: TelemetryCache) -> None:
        if len(data) < 5:
            return
        gear_code = int(data[4])
        is_reverse = gear_code == self._reverse_code
        cache.set_reverse(is_reverse)
        if self._debug:
            log.debug(
                "T856 IO raw-computed values: gear_code=%s reverse=%s",
                gear_code,
                is_reverse,
            )

    def _decode_doors(self, data: bytes, cache: TelemetryCache) -> None:
        if len(data) < 6:
            for door in range(1, self._door_count + 1):
                cache.set_door(str(door), self._door_unknown_state)
            return
        for door in range(1, self._door_count + 1):
            state = _door_api_state(data, door)
            cache.set_door(str(door), state)
            if self._debug:
                log.debug(
                    "T856 Doors raw-computed values: door=%s api_state=%s",
                    door,
                    state,
                )

    def _compute_inside_average(self) -> float | None:
        if self._average_all_zone:
            values: list[float] = []
            for sid in self._sensor_selection:
                values.extend(self._inside_queues.get(sid, []))
            return _avg(values)
        sid = self._sensor_selection[0]
        return _avg(self._inside_queues.get(sid, []))


def _door_api_state(data: bytes, door_idx: int) -> str:
    opening = _door_status(data, door_idx, "opening")
    closing = _door_status(data, door_idx, "closing")
    closed = _door_status(data, door_idx, "closed")
    if opening or closing:
        return "open"
    if closed:
        return "close"
    return "open"


def _door_status(data: bytes, door_idx: int, kind: str) -> bool:
    """PDF §2.6: 2-bit field value 1 means status active."""
    if door_idx < 1 or door_idx > 8:
        return False
    if door_idx <= 4:
        byte_base = {"opening": 0, "closed": 1, "closing": 2}[kind]
        shift = (door_idx - 1) * 2
    else:
        byte_base = {"opening": 3, "closed": 4, "closing": 5}[kind]
        shift = (door_idx - 5) * 2
    if byte_base >= len(data):
        return False
    field = (int(data[byte_base]) >> shift) & 0b11
    return field == 1


def _as_dict(v: Any) -> dict[str, Any]:
    return v if isinstance(v, dict) else {}


def _j1939_pgn(arbitration_id: int) -> int:
    return (int(arbitration_id) >> 8) & 0x3FFFF


def _to_number(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_sensors(raw: Any) -> list[int]:
    if isinstance(raw, str) and raw.strip().lower() == "all":
        return [1, 2]
    if isinstance(raw, Iterable) and not isinstance(raw, (str, bytes, dict)):
        out: list[int] = []
        for item in raw:
            try:
                sid = int(item)
            except (TypeError, ValueError):
                continue
            if sid in (1, 2):
                out.append(sid)
        return sorted(set(out))
    return [1, 2]


def _parse_id_set(raw: Any, default: int) -> set[int]:
    if raw is None:
        return {default}
    if isinstance(raw, (int, str)):
        values = [_parse_id(raw)]
    elif isinstance(raw, Iterable) and not isinstance(raw, (bytes, dict)):
        values = [_parse_id(item) for item in raw]
    else:
        values = []
    parsed = {v for v in values if v is not None}
    return parsed or {default}


def _parse_id(value: Any) -> int | None:
    if isinstance(value, int):
        return int(value)
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            return int(s, 0)
        except ValueError:
            return None
    return None


def _avg(values: Iterable[float]) -> float | None:
    vals = list(values)
    if not vals:
        return None
    return sum(vals) / len(vals)
