from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models.data_models import CanConfig

try:
    import can
except ImportError:
    can = None  # type: ignore[assignment]


def open_bus(cfg: CanConfig, logger: logging.Logger):
    """Open python-can Bus; returns None if python-can unavailable."""
    if can is None:
        logger.error("python-can not installed")
        return None
    try:
        bus = can.Bus(
            interface=cfg.interface,
            channel=cfg.channel,
            bitrate=cfg.bitrate,
            fd=cfg.fd,
        )
        logger.info(
            "CAN bus open: interface=%s channel=%s bitrate=%s",
            cfg.interface,
            cfg.channel,
            cfg.bitrate,
        )
        return bus
    except Exception as e:
        logger.exception("Failed to open CAN bus: %s", e)
        return None


def shutdown_bus(bus, logger: logging.Logger) -> None:
    if bus is None:
        return
    try:
        bus.shutdown()
    except Exception as e:
        logger.warning("CAN bus shutdown: %s", e)
