from __future__ import annotations

import asyncio
import random
import time
from typing import Any, Literal

from models.data_models import CacheConfig, TelemetryConfig

DoorState = Literal["unknown", "open", "close"]


class TelemetryCache:
    """
    In-memory telemetry snapshot. Mutations (set_*) must be called only while
    `async with cache.lock` is held by the CAN reader or temperature simulator.
    """

    def __init__(
        self,
        cache_cfg: CacheConfig,
        telemetry_cfg: TelemetryConfig,
        mapping_cfg: dict[str, Any] | None = None,
    ) -> None:
        self._cache_cfg = cache_cfg
        self._telem_cfg = telemetry_cfg
        self._mapping_cfg = mapping_cfg or {}
        temp_map = self._mapping_cfg.get("temperature", {})
        self.lock = asyncio.Lock()
        dc = cache_cfg.door_count
        self._doors: dict[str, str] = {
            str(i): cache_cfg.default_door_state for i in range(1, dc + 1)
        }
        self._door_ts: dict[str, float] = {
            str(i): 0.0 for i in range(1, dc + 1)
        }
        self._reverse = False
        self._reverse_ts: float = 0.0
        self._temperatures: dict[str, float] = {
            "inside": telemetry_cfg.sim_target_inside,
            "outside": telemetry_cfg.sim_target_outside,
        }
        self._temp_ts: dict[str, float] = {
            "inside": 0.0,
            "outside": 0.0,
        }
        self._pgn_last_mono: dict[int, float] = {}
        self._frame_counters: dict[int, int] = {}
        self._temp_defaults: dict[str, float | None] = {
            "inside": _as_optional_float(
                temp_map.get("interior-default-value")
                if isinstance(temp_map, dict)
                else None
            ),
            "outside": _as_optional_float(
                temp_map.get("exterior-default-value")
                if isinstance(temp_map, dict)
                else None
            ),
        }
        self._temp_norm: dict[str, tuple[float, float, float, float]] = {
            "inside": (
                _as_float(temp_map, "interior-normalize-min", -40.0),
                _as_float(temp_map, "interior-normalize-max", 210.0),
                _as_float(temp_map, "interior-normalize-fallback-min", -50.0),
                _as_float(temp_map, "interior-normalize-fallback-max", 250.0),
            ),
            "outside": (
                _as_float(temp_map, "exterior-normalize-min", -40.0),
                _as_float(temp_map, "exterior-normalize-max", 210.0),
                _as_float(temp_map, "exterior-normalize-fallback-min", -50.0),
                _as_float(temp_map, "exterior-normalize-fallback-max", 250.0),
            ),
        }

    # --- sync writers (caller must hold self.lock) ---

    def set_door(self, door_id: str, state: str) -> None:
        if door_id in self._doors:
            self._doors[door_id] = state
            self._door_ts[door_id] = time.monotonic()

    def set_reverse(self, value: bool) -> None:
        self._reverse = value
        self._reverse_ts = time.monotonic()

    def set_temperature(self, zone: str, value: float) -> None:
        self._temperatures[zone] = value
        self._temp_ts[zone] = time.monotonic()

    def pgn_throttle_skip(self, pgn_key: int) -> bool:
        cfg = self._cache_cfg
        now = time.monotonic()
        if cfg.min_interval_per_pgn_ms is not None:
            last = self._pgn_last_mono.get(pgn_key, 0.0)
            if last > 0.0 and (now - last) * 1000.0 < cfg.min_interval_per_pgn_ms:
                return True
        if cfg.process_every_n_frames is not None and cfg.process_every_n_frames > 1:
            c = self._frame_counters.get(pgn_key, 0) + 1
            self._frame_counters[pgn_key] = c
            if c % cfg.process_every_n_frames != 0:
                return True
        return False

    def pgn_mark_done(self, pgn_key: int) -> None:
        self._pgn_last_mono[pgn_key] = time.monotonic()

    # --- simulation step (caller holds lock) ---

    def step_simulated_temperatures(self) -> None:
        cfg = self._telem_cfg
        for zone, target in (
            ("inside", cfg.sim_target_inside),
            ("outside", cfg.sim_target_outside),
        ):
            cur = self._temperatures.get(zone, target)
            step = cfg.sim_step_c
            if step <= 0:
                continue
            drift = cur - target
            if abs(drift) >= cfg.sim_max_drift_c:
                delta = -step if drift > 0 else step
            else:
                delta = random.choice([-step, step])
            new_v = max(
                target - cfg.sim_max_drift_c,
                min(target + cfg.sim_max_drift_c, cur + delta),
            )
            self.set_temperature(zone, round(new_v, 1))

    # --- async readers for API ---

    def _door_state_api(self, door_id: str) -> DoorState:
        now = time.monotonic()
        ts = self._door_ts.get(door_id, 0.0)
        if ts <= 0.0 or (now - ts) > self._cache_cfg.stale_after_seconds:
            return "unknown"
        s = self._doors.get(door_id, "unknown")
        if s in ("unknown", "open", "close"):
            return s  # type: ignore[return-value]
        return "unknown"

    def _reverse_api(self) -> bool:
        now = time.monotonic()
        if self._reverse_ts <= 0.0 or (now - self._reverse_ts) > self._cache_cfg.stale_after_seconds:
            return False
        return self._reverse

    def _temperatures_api(self) -> dict[str, float]:
        if self._telem_cfg.temperature_mode == "simulated":
            return dict(self._temperatures)
        now = time.monotonic()
        out: dict[str, float] = {}
        for z in ("inside", "outside"):
            ts = self._temp_ts.get(z, 0.0)
            is_fresh = ts > 0.0 and (now - ts) <= self._cache_cfg.stale_after_seconds
            if is_fresh:
                out[z] = self._normalize_temperature(z, self._temperatures[z])
                continue
            default_v = self._temp_defaults.get(z)
            if default_v is not None:
                out[z] = self._normalize_temperature(z, default_v)
        return out

    async def snapshot_doors(self) -> dict[str, str]:
        async with self.lock:
            return {k: self._door_state_api(k) for k in sorted(self._doors.keys(), key=int)}

    async def snapshot_gear(self) -> bool:
        async with self.lock:
            return self._reverse_api()

    async def snapshot_temperatures(self) -> dict[str, float]:
        async with self.lock:
            temps = self._temperatures_api()
            if self._telem_cfg.temperature_mode == "can" and not temps:
                return {}
            if self._telem_cfg.temperature_mode == "simulated":
                return dict(self._temperatures)
            return temps

    def _normalize_temperature(self, zone: str, value: float) -> float:
        min_v, max_v, fallback_min, fallback_max = self._temp_norm.get(
            zone, (-40.0, 210.0, -50.0, 250.0)
        )
        if value < min_v:
            return fallback_min
        if value > max_v:
            return fallback_max
        return value


def _as_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_float(raw: Any, key: str, default: float) -> float:
    if not isinstance(raw, dict):
        return default
    v = raw.get(key, default)
    try:
        return float(v)
    except (TypeError, ValueError):
        return default
