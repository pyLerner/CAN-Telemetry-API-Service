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
        system=SystemConfig(program_directory="/tmp", log_dir="logs", disable_can=True),
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
    cache = TelemetryCache(cfg, tcfg)
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


if __name__ == "__main__":
    import subprocess

    raise SystemExit(
        subprocess.call([sys.executable, "-m", "pytest", __file__, *sys.argv[1:]])
    )
