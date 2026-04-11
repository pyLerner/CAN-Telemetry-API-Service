from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI
from models.data_models import AppConfig
from telemetry.cache import TelemetryCache


def _json_keys_to_kebab(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {
            k.replace("_", "-"): _json_keys_to_kebab(v) for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_json_keys_to_kebab(i) for i in obj]
    return obj


def create_app(cfg: AppConfig, cache: TelemetryCache, logger: logging.Logger) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        logger.info("API binding %s:%s", cfg.api.host, cfg.api.port)
        yield

    app = FastAPI(title="CAN Telemetry API", version="1.0", lifespan=lifespan)

    @app.get("/api/ping")
    async def ping() -> dict[str, Any]:
        body = {
            "running": "ok",
            "timestamp": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        }
        return _json_keys_to_kebab(body)

    @app.get("/api/telemetry/v1/doors/state")
    async def doors_state() -> dict[str, Any]:
        doors = await cache.snapshot_doors()
        return _json_keys_to_kebab({"doors": doors})

    @app.get("/api/telemetry/v1/gear/state")
    async def gear_state() -> dict[str, Any]:
        rev = await cache.snapshot_gear()
        return _json_keys_to_kebab({"reverse": rev})

    @app.get("/api/telemetry/v1/temperature/state")
    async def temperature_state() -> dict[str, Any]:
        temps = await cache.snapshot_temperatures()
        return _json_keys_to_kebab({"temperatures": temps})

    return app
