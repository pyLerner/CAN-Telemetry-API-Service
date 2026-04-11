from __future__ import annotations

import asyncio
import logging
from typing import Any

from vehicle_can.decoders.base import CanTelemetryDecoder, j1939_pgn_from_id
from models.data_models import AppConfig
from telemetry.cache import TelemetryCache


def _throttle_enabled(cache_cfg) -> bool:
    if cache_cfg.min_interval_per_pgn_ms is not None:
        return True
    if (
        cache_cfg.process_every_n_frames is not None
        and cache_cfg.process_every_n_frames > 1
    ):
        return True
    return False


async def can_reader_task(
    cfg: AppConfig,
    cache: TelemetryCache,
    decoder: CanTelemetryDecoder,
    bus: Any,
    logger: logging.Logger,
) -> None:
    if bus is None:
        logger.info("CAN reader not started (no bus)")
        return
    timeout = cfg.can.receive_timeout
    th = _throttle_enabled(cfg.cache)
    while True:
        try:

            def _recv() -> Any:
                return bus.recv(timeout=timeout)

            msg = await asyncio.to_thread(_recv)
        except asyncio.CancelledError:
            logger.info("CAN reader task cancelled")
            break
        except Exception as e:
            logger.exception("CAN recv error: %s", e)
            await asyncio.sleep(1.0)
            continue
        if msg is None:
            continue
        pgn_key = (
            j1939_pgn_from_id(msg.arbitration_id)
            if getattr(msg, "is_extended_id", False)
            else int(msg.arbitration_id)
        )
        async with cache.lock:
            if th:
                if cache.pgn_throttle_skip(pgn_key):
                    continue
                decoder.decode_frame(msg, cache)
                cache.pgn_mark_done(pgn_key)
            else:
                decoder.decode_frame(msg, cache)


async def temperature_sim_task(
    cfg: AppConfig,
    cache: TelemetryCache,
    logger: logging.Logger,
) -> None:
    if cfg.telemetry.temperature_mode != "simulated":
        return
    interval = max(cfg.telemetry.sim_tick_seconds, 0.1)
    logger.info("Temperature simulation enabled (tick=%s s)", interval)
    while True:
        try:
            await asyncio.sleep(interval)
            async with cache.lock:
                cache.step_simulated_temperatures()
        except asyncio.CancelledError:
            logger.info("Temperature sim task cancelled")
            break
        except Exception as e:
            logger.exception("Temperature sim error: %s", e)
