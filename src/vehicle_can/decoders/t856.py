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

    def configure(self, mapping: dict[str, Any]) -> None:
        temp_cfg = _as_dict(mapping.get("temperature"))
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

    def decode_frame(self, msg: Any, cache: TelemetryCache) -> None:
        arb = int(msg.arbitration_id)
        data = bytes(msg.data)
        if arb == self._ID_TEMPERATURES1:
            self._decode_temperatures1(data, cache)
            return
        if arb == self._ID_IO:
            self._decode_io(data, cache)
            return
        if arb == self._ID_DOORS:
            self._decode_doors(data, cache)

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
        if len(data) < 6:
            return
        # Doors: all states except "closed" are treated as open.
        for door in range(1, 9):
            closed_bit = _door_status(data, door, "closed")
            state = "close" if closed_bit else "open"
            cache.set_door(str(door), state)
            if self._debug:
                log.debug(
                    "T856 Doors raw-computed values: door=%s closed=%s api_state=%s",
                    door,
                    closed_bit,
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


def _as_dict(v: Any) -> dict[str, Any]:
    return v if isinstance(v, dict) else {}


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


def _avg(values: Iterable[float]) -> float | None:
    vals = list(values)
    if not vals:
        return None
    return sum(vals) / len(vals)


def _door_status(data: bytes, door_idx: int, kind: str) -> bool:
    # Each status is encoded as a 2-bit field where 1 means active.
    # Door1..4 are in bytes 0..2, Door5..8 are in bytes 3..5.
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
    field = (data[byte_base] >> shift) & 0b11
    return field == 1
