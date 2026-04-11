from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

import can  # python-can (import before cantools; cantools expects this module)
import cantools

if TYPE_CHECKING:
    from telemetry.cache import TelemetryCache

log = logging.getLogger("can-telemetry.dbc")


class DbcGenericDecoder:
    """
    Decode frames using a DBC file and optional [Mapping.signal_map] table:
    door_1..door_N -> signal name, reverse -> signal, inside/outside -> signal.
    """

    def __init__(self) -> None:
        self._db: cantools.database.Database | None = None
        self._signal_map: dict[str, str] = {}

    def configure(self, mapping: dict[str, Any]) -> None:
        path = mapping.get("dbc_path") or mapping.get("DbcPath")
        if not path:
            log.warning("DbcGenericDecoder: no dbc_path in Mapping; decoder is inactive")
            self._db = None
            self._signal_map = {}
            return
        p = Path(str(path))
        if not p.is_file():
            log.error("DbcGenericDecoder: DBC file not found: %s", p)
            self._db = None
            self._signal_map = {}
            return
        self._db = cantools.database.load_file(str(p))
        sm = mapping.get("signal_map") or mapping.get("SignalMap") or {}
        self._signal_map = {str(k).lower(): str(v) for k, v in sm.items()}

    def decode_frame(self, msg: can.Message, cache: TelemetryCache) -> None:
        if self._db is None:
            return
        try:
            decoded = self._db.decode_message(
                msg.arbitration_id,
                msg.data,
                decode_choices=False,
            )
        except Exception:
            return
        if not isinstance(decoded, dict):
            return

        def sig_val(name: str) -> float | int | str | None:
            if name not in decoded:
                return None
            return decoded[name]  # type: ignore[no-any-return]

        for door_key, sig in self._signal_map.items():
            if door_key.startswith("door_"):
                vid = door_key.removeprefix("door_")
                v = sig_val(sig)
                if v is None:
                    continue
                state = _door_from_value(v)
                if state:
                    cache.set_door(vid, state)

        rev_sig = self._signal_map.get("reverse")
        if rev_sig:
            v = sig_val(rev_sig)
            if v is not None:
                cache.set_reverse(
                    bool(int(v))
                    if isinstance(v, (int, float))
                    else str(v).lower() in ("1", "true", "on")
                )

        for zone, key in (("inside", "inside"), ("outside", "outside")):
            sig = self._signal_map.get(key)
            if not sig:
                continue
            v = sig_val(sig)
            if v is None:
                continue
            try:
                cache.set_temperature(zone, float(v))
            except (TypeError, ValueError):
                pass


def _door_from_value(v: float | int | str) -> str | None:
    if isinstance(v, str):
        low = v.lower()
        if low in ("open", "closed", "close"):
            return "open" if low == "open" else "close"
    if isinstance(v, (int, float)):
        if int(v) == 1:
            return "open"
        if int(v) == 0:
            return "close"
    return None
