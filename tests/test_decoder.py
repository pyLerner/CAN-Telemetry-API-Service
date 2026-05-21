from __future__ import annotations

import sys
from pathlib import Path

# Allow `uv run tests/test_decoder.py` (plain Python); pytest sets pythonpath via pyproject.toml.
_proj_root = Path(__file__).resolve().parents[1]
_src_dir = _proj_root / "src"
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

import pytest
from telemetry.cache import TelemetryCache

from vehicle_can.decoders.dbc_generic import DbcGenericDecoder
from vehicle_can.decoders.noop import NoopDecoder
from vehicle_can.decoders.registry import build_decoder, load_decoder_class
from vehicle_can.decoders.t856 import T856Decoder
from models.data_models import (
    ApiConfig,
    AppConfig,
    CacheConfig,
    CanConfig,
    SystemConfig,
    TelemetryConfig,
)


def _minimal_app(mapping: dict, decoder: str = "noop") -> AppConfig:
    return AppConfig(
        api=ApiConfig(host="127.0.0.1", port=7080, workers=1),
        system=SystemConfig(
            program_directory="/tmp",
            log_dir="logs",
            disable_can=True,
            debug=False,
        ),
        can=CanConfig(
            interface="socketcan",
            channel="vcan0",
            bitrate=250_000,
            fd=False,
            profile="bus-fms",
            decoder=decoder,
            receive_timeout=0.1,
        ),
        cache=CacheConfig(
            stale_after_seconds=3600.0,
            default_door_state="unknown",
            coalesce_by_frame=True,
            door_count=4,
            min_interval_per_pgn_ms=None,
            process_every_n_frames=None,
        ),
        telemetry=TelemetryConfig(
            temperature_mode="can",
            sim_target_inside=22.0,
            sim_target_outside=15.0,
            sim_tick_seconds=5.0,
            sim_step_c=0.1,
            sim_max_drift_c=2.0,
        ),
        mapping=mapping,
    )


def test_load_builtin_decoder() -> None:
    cls = load_decoder_class("noop")
    assert cls is NoopDecoder


def test_build_decoder_from_config() -> None:
    cfg = _minimal_app({})
    d = build_decoder(cfg)
    assert isinstance(d, NoopDecoder)


@pytest.fixture
def tiny_dbc(tmp_path: Path) -> Path:
    content = '''VERSION ""

BU_: DBG

BO_ 256 TestMsg: 8 DBG
 SG_ Rev : 0|1@1+ (1,0) [0|1] "" DBG
 SG_ D1 : 1|1@1+ (1,0) [0|1] "" DBG
'''
    p = tmp_path / "test.dbc"
    p.write_text(content, encoding="utf-8")
    return p


def test_dbc_generic_updates_cache(tiny_dbc: Path) -> None:
    cfg = CacheConfig(
        stale_after_seconds=3600.0,
        default_door_state="unknown",
        coalesce_by_frame=True,
        door_count=4,
        min_interval_per_pgn_ms=None,
        process_every_n_frames=None,
    )
    tcfg = TelemetryConfig(
        temperature_mode="can",
        sim_target_inside=22.0,
        sim_target_outside=15.0,
        sim_tick_seconds=5.0,
        sim_step_c=0.1,
        sim_max_drift_c=2.0,
    )
    cache = TelemetryCache(cfg, tcfg, {})
    dec = DbcGenericDecoder()
    dec.configure(
        {
            "dbc_path": str(tiny_dbc),
            "signal_map": {"reverse": "Rev", "door_1": "D1"},
        }
    )

    class Msg:
        arbitration_id = 256
        is_extended_id = False
        data = bytes([0x03]).ljust(8, b"\x00")

    import asyncio

    async def _run() -> None:
        async with cache.lock:
            dec.decode_frame(Msg(), cache)

    asyncio.run(_run())
    assert cache._reverse is True
    assert cache._doors["1"] == "open"


def test_load_t856_decoder() -> None:
    cls = load_decoder_class("t856")
    assert cls is T856Decoder


def test_t856_decoder_temperature_reverse_and_doors() -> None:
    cfg = CacheConfig(
        stale_after_seconds=3600.0,
        default_door_state="unknown",
        coalesce_by_frame=True,
        door_count=4,
        min_interval_per_pgn_ms=None,
        process_every_n_frames=None,
    )
    tcfg = TelemetryConfig(
        temperature_mode="can",
        sim_target_inside=22.0,
        sim_target_outside=15.0,
        sim_tick_seconds=5.0,
        sim_step_c=0.1,
        sim_max_drift_c=2.0,
    )
    mapping = {
        "temperature": {
            "queue-len": 3,
            "average-all-zone": True,
            "sensors": [1, 2],
            "interior-default-value": None,
            "exterior-default-value": None,
            "interior-normalize-min": -40,
            "interior-normalize-max": 210,
            "interior-normalize-fallback-min": -50,
            "interior-normalize-fallback-max": 250,
            "exterior-normalize-min": -40,
            "exterior-normalize-max": 210,
            "exterior-normalize-fallback-min": -50,
            "exterior-normalize-fallback-max": 250,
        },
        "reverse": {"reverse-code": 124},
        "doors": {
            "unknown-state": "unknown",
        },
        "_cache": {"door-count": 4},
    }
    cache = TelemetryCache(cfg, tcfg, mapping)
    dec = T856Decoder()
    dec.configure(mapping)

    class TempMsg:
        arbitration_id = 0x18FF6227
        is_extended_id = True
        # sensor1=40 => 0 C, sensor2=41 => 1 C, outside raw=10 => -272.6875 C
        data = bytes([0x00, 40, 41, 0x00, 10, 0x00, 0x00, 0x00])

    class IoMsg:
        arbitration_id = 0x18FF6427
        is_extended_id = True
        data = bytes([0x00, 0x00, 0x00, 0x00, 124, 0x00, 0x00, 0x00])

    class DoorMsg:
        arbitration_id = 0x18FF6527
        is_extended_id = True
        # door 1 open plateau from debug/20260521/1-closed-opened-closed.log
        data = bytes.fromhex("0154000005000000")

    import asyncio

    async def _run() -> None:
        async with cache.lock:
            dec.decode_frame(TempMsg(), cache)
            dec.decode_frame(IoMsg(), cache)
            dec.decode_frame(DoorMsg(), cache)

    asyncio.run(_run())
    assert cache._reverse is True
    assert cache._doors["1"] == "open"
    assert cache._doors["2"] == "close"
    # average before normalization = (0 + 1) / 2
    assert cache._temperatures["inside"] == pytest.approx(0.5)

    temps = asyncio.run(cache.snapshot_temperatures())
    # outside value is normalized by API layer due to lower threshold.
    assert temps["outside"] == -50


def test_t856_forces_average_all_zone_with_multiple_sensors(caplog: pytest.LogCaptureFixture) -> None:
    dec = T856Decoder()
    with caplog.at_level("ERROR"):
        dec.configure(
            {
                "temperature": {
                    "queue-len": 5,
                    "average-all-zone": False,
                    "sensors": [1, 2],
                }
            }
        )
    assert dec._average_all_zone is True
    assert "Forcing average-all-zone=true" in caplog.text


def test_t856_decoder_accepts_configured_pgn_mode() -> None:
    cfg = CacheConfig(
        stale_after_seconds=3600.0,
        default_door_state="unknown",
        coalesce_by_frame=True,
        door_count=4,
        min_interval_per_pgn_ms=None,
        process_every_n_frames=None,
    )
    tcfg = TelemetryConfig(
        temperature_mode="can",
        sim_target_inside=22.0,
        sim_target_outside=15.0,
        sim_tick_seconds=5.0,
        sim_step_c=0.1,
        sim_max_drift_c=2.0,
    )
    cache = TelemetryCache(cfg, tcfg, {})
    dec = T856Decoder()
    dec.configure(
        {
            "doors": {
                "unknown-state": "unknown",
            },
            "_cache": {"door-count": 4},
            "ids": {
                "doors": ["0xFF65"],
                "match-mode": "pgn",
            }
        }
    )

    class DoorMsg:
        arbitration_id = 0x18FF6501
        is_extended_id = True
        data = bytes.fromhex("0055000005000000")

    import asyncio

    async def _run() -> None:
        async with cache.lock:
            dec.decode_frame(DoorMsg(), cache)

    asyncio.run(_run())
    assert cache._doors["1"] == "close"


if __name__ == "__main__":
    import subprocess

    raise SystemExit(
        subprocess.call([sys.executable, "-m", "pytest", __file__, *sys.argv[1:]])
    )
