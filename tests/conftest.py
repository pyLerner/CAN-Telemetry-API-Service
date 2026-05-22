from __future__ import annotations

import sys
from pathlib import Path

# Ensure `src` is importable when this file is loaded outside pytest (e.g. `python tests/conftest.py`).
_root = Path(__file__).resolve().parents[1]
_src_dir = str(_root / "src")
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

import asyncio
import logging
from collections.abc import Generator
import pytest
from api_server import create_app
from models.data_models import (
    ApiConfig,
    AppConfig,
    CacheConfig,
    CanConfig,
    SystemConfig,
    TelemetryConfig,
)
from starlette.testclient import TestClient
from telemetry.cache import TelemetryCache


def _make_cfg() -> AppConfig:
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
            decoder="noop",
            receive_timeout=0.1,
        ),
        cache=CacheConfig(
            stale_after_seconds=3600.0,
            default_door_state="unknown",
            coalesce_by_frame=True,
            door_count=6,
            min_interval_per_pgn_ms=None,
            process_every_n_frames=None,
        ),
        telemetry=TelemetryConfig(
            temperature_mode="simulated",
            sim_target_inside=22.0,
            sim_target_outside=15.0,
            sim_tick_seconds=5.0,
            sim_step_c=0.1,
            sim_max_drift_c=2.0,
        ),
        mapping={},
    )


def _null_logger() -> logging.Logger:
    log = logging.getLogger("pytest-can-telemetry")
    log.handlers.clear()
    log.addHandler(logging.NullHandler())
    log.setLevel(logging.DEBUG)
    return log


@pytest.fixture
def app_config() -> AppConfig:
    return _make_cfg()


@pytest.fixture
def logger() -> logging.Logger:
    return _null_logger()


@pytest.fixture
def cache(app_config: AppConfig) -> TelemetryCache:
    return TelemetryCache(app_config.cache, app_config.telemetry, app_config.mapping)


@pytest.fixture
def app(app_config: AppConfig, cache: TelemetryCache, logger: logging.Logger):
    return create_app(app_config, cache, logger)


@pytest.fixture
def client(app) -> Generator[TestClient, None, None]:
    with TestClient(app) as c:
        yield c


async def _seed_doors(cache: TelemetryCache) -> None:
    async with cache.lock:
        states = {
            "1": "close",
            "2": "open",
            "3": "close",
            "4": "close",
            "5": "open",
            "6": "close",
        }
        for door_id, state in states.items():
            cache.set_door(door_id, state)
        cache.set_reverse(False)


@pytest.fixture
def client_seeded(app_config: AppConfig, logger: logging.Logger) -> Generator[TestClient, None, None]:
    cache = TelemetryCache(app_config.cache, app_config.telemetry, app_config.mapping)
    asyncio.run(_seed_doors(cache))
    app = create_app(app_config, cache, logger)
    with TestClient(app) as c:
        yield c


if __name__ == "__main__":
    # Running this file only loads fixtures; it does not execute tests. `-v` is not pytest's verbose.
    print(
        "conftest.py only registers pytest fixtures; it is not a test runner.\n"
        "Run tests: uv run pytest tests/ -v",
        file=sys.stderr,
    )
