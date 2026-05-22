"""Door decode tests against stable payloads from debug/20260521/."""

from __future__ import annotations

import re
import sys
from pathlib import Path

_proj_root = Path(__file__).resolve().parents[1]
_src_dir = _proj_root / "src"
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

import pytest
from telemetry.cache import TelemetryCache

from models.data_models import CacheConfig, TelemetryConfig
from vehicle_can.decoders.t856 import T856Decoder, _door_api_state

_LOG_DIR = _proj_root / "debug" / "20260521"
_CAN_LINE = re.compile(
    r"\s+can\d+\s+([0-9A-Fa-f]+)\s+\[\d+\]\s+((?:[0-9A-Fa-f]{2}\s*)+)"
)

# Stable plateaus from field logs (not transitional frames).
_ALL_CLOSED = bytes.fromhex("0055000005000000")
_ALL_OPENED = bytes.fromhex("0000000000000000")

_PER_DOOR_OPEN: dict[int, bytes] = {
    1: bytes.fromhex("0154000005000000"),
    2: bytes.fromhex("0451000005000000"),
    3: bytes.fromhex("1045000005000000"),
    4: bytes.fromhex("4015000005000000"),
    5: bytes.fromhex("0055000104000000"),
    6: bytes.fromhex("0055000401000000"),
}


def _parse_payloads(log_name: str) -> list[bytes]:
    path = _LOG_DIR / log_name
    out: list[bytes] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = _CAN_LINE.match(line)
        if not m:
            continue
        if int(m.group(1), 16) != 0x18FF6527:
            continue
        out.append(bytes.fromhex(m.group(2).replace(" ", "")))
    return out


def _decode_all(dec: T856Decoder, data: bytes, door_count: int = 6) -> dict[str, str]:
    cache_cfg = CacheConfig(
        stale_after_seconds=3600.0,
        default_door_state="unknown",
        coalesce_by_frame=True,
        door_count=door_count,
        min_interval_per_pgn_ms=None,
        process_every_n_frames=None,
    )
    cfg = TelemetryCache(
        cache_cfg,
        TelemetryConfig(
            temperature_mode="can",
            sim_target_inside=22.0,
            sim_target_outside=15.0,
            sim_tick_seconds=5.0,
            sim_step_c=0.1,
            sim_max_drift_c=2.0,
        ),
        {},
    )
    dec.configure({"doors": {"unknown-state": "unknown"}, "_cache": {"door-count": door_count}})
    import asyncio

    class Msg:
        arbitration_id = 0x18FF6527
        is_extended_id = True

        def __init__(self, payload: bytes) -> None:
            self.data = payload

    async def _run() -> dict[str, str]:
        async with cfg.lock:
            dec.decode_frame(Msg(data), cfg)
            return dict(cfg._doors)

    return asyncio.run(_run())


@pytest.mark.parametrize(
    ("payload", "door", "expected"),
    [
        (_ALL_CLOSED, d, "close")
        for d in range(1, 7)
    ]
    + [
        (_ALL_OPENED, d, "open")
        for d in range(1, 7)
    ],
)
def test_plateau_all_doors(payload: bytes, door: int, expected: str) -> None:
    assert _door_api_state(payload, door) == expected


@pytest.mark.parametrize("door", range(1, 7))
def test_plateau_single_door_open(door: int) -> None:
    payload = _PER_DOOR_OPEN[door]
    for d in range(1, 7):
        want = "open" if d == door else "close"
        assert _door_api_state(payload, d) == want


def test_all_closed_log_majority_close() -> None:
    payloads = _parse_payloads("all-closed.log")
    assert payloads
    for data in payloads:
        for d in range(1, 7):
            assert _door_api_state(data, d) == "close"


def test_all_opened_log_majority_open() -> None:
    payloads = _parse_payloads("all-opened.log")
    assert payloads
    for data in payloads:
        for d in range(1, 7):
            assert _door_api_state(data, d) == "open"


@pytest.mark.parametrize(
    ("log_name", "door"),
    [(f"{n}-closed-opened-closed.log", n) for n in range(1, 7)],
)
def test_per_door_log_open_plateau(log_name: str, door: int) -> None:
    payloads = _parse_payloads(log_name)
    assert payloads
    plateau = _PER_DOOR_OPEN[door]
    hits = sum(1 for p in payloads if p == plateau)
    assert hits >= 10, f"expected stable open plateau in {log_name}, got {hits}"
    for data in payloads:
        if data != plateau:
            continue
        for d in range(1, 7):
            want = "open" if d == door else "close"
            assert _door_api_state(data, d) == want


def test_all_closed_opened_closed_phases() -> None:
    payloads = _parse_payloads("all-closed-opened-closed.log")
    assert payloads
    closed_hits = sum(1 for p in payloads if p == _ALL_CLOSED)
    open_hits = sum(1 for p in payloads if p == _ALL_OPENED)
    assert closed_hits >= 10
    assert open_hits >= 10
    for data in payloads:
        if data == _ALL_CLOSED:
            assert all(_door_api_state(data, d) == "close" for d in range(1, 7))
        elif data == _ALL_OPENED:
            assert all(_door_api_state(data, d) == "open" for d in range(1, 7))


def test_decoder_integration_all_closed() -> None:
    dec = T856Decoder()
    doors = _decode_all(dec, _ALL_CLOSED)
    assert all(doors[str(d)] == "close" for d in range(1, 7))
