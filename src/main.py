from __future__ import annotations

import argparse
import asyncio
import signal
import sys
from pathlib import Path
from typing import Any

_SRC = Path(__file__).resolve().parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import uvicorn
from api_server import create_app
from vehicle_can.bus import open_bus, shutdown_bus
from vehicle_can.decoders.registry import build_decoder
from log_config.log_config import setup_logger
from models.data_models import load_config
from runner_task import can_reader_task, temperature_sim_task
from telemetry.cache import TelemetryCache


async def main_async(args: argparse.Namespace) -> None:
    config_path = Path(args.config)
    cfg = load_config(config_path)

    Path(cfg.system.log_dir).mkdir(parents=True, exist_ok=True)
    log_file = Path(cfg.system.log_dir) / "can-telemetry.log"
    logger = setup_logger(log_file)

    logger.info("=== CAN Telemetry API starting ===")
    logger.info("Config: %s | decoder=%s | disable_can=%s", config_path, cfg.can.decoder, cfg.system.disable_can)

    cache = TelemetryCache(cfg.cache, cfg.telemetry)
    decoder = build_decoder(cfg)
    bus = None
    if not cfg.system.disable_can:
        bus = open_bus(cfg.can, logger)

    app = create_app(cfg, cache, logger)

    workers = cfg.api.workers
    if workers != 1:
        logger.warning("Workers=%s not supported for in-memory cache; using 1", workers)
        workers = 1
    uv_cfg = uvicorn.Config(
        app=app,
        host=cfg.api.host,
        port=cfg.api.port,
        workers=workers,
        log_level="info",
        loop="asyncio",
    )
    server = uvicorn.Server(config=uv_cfg)

    reader_t = asyncio.create_task(
        can_reader_task(cfg, cache, decoder, bus, logger),
        name="can_reader",
    )
    sim_t = asyncio.create_task(
        temperature_sim_task(cfg, cache, logger),
        name="temperature_sim",
    )
    asyncio.create_task(server.serve(), name="api_server")

    shutdown_event = asyncio.Event()

    def _handle_signal(sig: int, frame: Any | None) -> None:
        logger.info("Received signal %s, shutting down...", sig)
        shutdown_event.set()

    for s in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(s, _handle_signal)
        except Exception:
            pass

    await shutdown_event.wait()

    for t in (reader_t, sim_t):
        t.cancel()
    await asyncio.gather(reader_t, sim_t, return_exceptions=True)

    await server.shutdown()

    shutdown_bus(bus, logger)
    logger.info("=== CAN Telemetry API stopped ===")


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="CAN telemetry REST API service")
    ap.add_argument(
        "--config",
        type=Path,
        default=Path("etc/telemetry-provider.toml"),
        help="Path to TOML configuration",
    )
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
