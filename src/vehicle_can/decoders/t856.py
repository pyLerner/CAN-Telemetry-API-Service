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
    Door mapping note (empirical per-door):
    - Per-door telemetry is decoded from 2-bit fields in bytes 0 and 4 of
      0x1BFFD880 frames, based on 1-door..6-door field dumps.
    - Default field layout for 6 doors:
      door1=(byte0,shift2), door2=(byte0,shift4), door3=(byte0,shift6),
      door4=(byte4,shift2), door5=(byte4,shift4), door6=(byte4,shift6).
    - Default state map: field value 3 => open, values 0/1/2 => close.
    - The old by-document model is archived in t856.py.bydoc.arvhived.

    Decoder for T856 requirements:
    - 0x18FF6227 Temperatures1
    - 0x18FF6427 IO (reverse)
    - 0x18FF6527 Doors
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
        self._door_map: dict[int, DoorRule] = {}
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
        self._door_map = _build_door_map(self._door_count, door_cfg.get("door-map"))
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
                "door_count=%s probe_bytes=%s open_codes=%s close_codes=%s unknown=%s",
                self._id_match_mode,
                sorted(hex(i) for i in self._door_ids),
                sorted(hex(i) for i in self._io_ids),
                sorted(hex(i) for i in self._temperature_ids),
                self._door_count,
                {k: (v.byte, v.shift, sorted(v.open_values), sorted(v.close_values)) for k, v in self._door_map.items()},
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
        # 8-bit values, 1 C/bit with offset -40
        sensor_raw = {
            1: float(int(data[1]) - 40),
            2: float(int(data[2]) - 40),
        }
        for sid, val in sensor_raw.items():
            q = self._inside_queues.get(sid)
            if q is not None:
                q.append(val)

        # 16-bit external temperature, factor 0.03125, offset -273
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
        if len(data) < 5:
            return
        for door in range(1, self._door_count + 1):
            state = self._decode_one_door(data, door)
            cache.set_door(str(door), state)
            if self._debug:
                log.debug(
                    "T856 Doors raw-computed values: door=%s api_state=%s",
                    door,
                    state,
                )

    def _decode_one_door(self, data: bytes, door_idx: int) -> str:
        rule = self._door_map.get(door_idx)
        if rule is None:
            return self._door_unknown_state
        if rule.byte >= len(data):
            return self._door_unknown_state
        field = (int(data[rule.byte]) >> rule.shift) & 0b11
        if field in rule.open_values:
            return "open"
        if field in rule.close_values:
            return "close"
        return self._door_unknown_state

    def _compute_inside_average(self) -> float | None:
        if self._average_all_zone:
            values: list[float] = []
            for sid in self._sensor_selection:
                values.extend(self._inside_queues.get(sid, []))
            return _avg(values)
        sid = self._sensor_selection[0]
        return _avg(self._inside_queues.get(sid, []))


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


def _parse_code_set(raw: Any, default: set[int]) -> set[int]:
    if raw is None:
        return set(default)
    if isinstance(raw, (int, str)):
        parsed = {_parse_id(raw)}
    elif isinstance(raw, Iterable) and not isinstance(raw, (bytes, dict)):
        parsed = {_parse_id(item) for item in raw}
    else:
        parsed = set()
    out = {v for v in parsed if v is not None and 0 <= v <= 0xFF}
    return out or set(default)


class DoorRule:
    def __init__(
        self, byte: int, shift: int, open_values: set[int], close_values: set[int]
    ) -> None:
        self.byte = byte
        self.shift = shift
        self.open_values = open_values
        self.close_values = close_values


def _build_default_door_map(door_count: int) -> dict[int, DoorRule]:
    slots = [(0, 2), (0, 4), (0, 6), (4, 2), (4, 4), (4, 6)]
    out: dict[int, DoorRule] = {}
    for door in range(1, door_count + 1):
        byte, shift = slots[(door - 1) % len(slots)]
        out[door] = DoorRule(byte, shift, {3}, {0, 1, 2})
    return out


def _build_door_map(door_count: int, raw_map: Any) -> dict[int, DoorRule]:
    out = _build_default_door_map(door_count)
    cfg = _as_dict(raw_map)
    for k, v in cfg.items():
        try:
            door = int(str(k))
        except ValueError:
            continue
        if door < 1 or door > door_count:
            continue
        item = _as_dict(v)
        b = _parse_id(item.get("byte"))
        s = _parse_id(item.get("shift"))
        if b is None or s is None or b < 0 or b > 7 or s not in (0, 2, 4, 6):
            continue
        open_values = _parse_code_set(item.get("open-values"), {3})
        close_values = _parse_code_set(item.get("close-values"), {0, 1, 2})
        out[door] = DoorRule(b, s, {x & 0b11 for x in open_values}, {x & 0b11 for x in close_values})
    return out


def _avg(values: Iterable[float]) -> float | None:
    vals = list(values)
    if not vals:
        return None
    return sum(vals) / len(vals)
