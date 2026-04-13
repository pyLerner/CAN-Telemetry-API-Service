from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ApiConfig:
    host: str
    port: int
    workers: int


@dataclass(frozen=True)
class SystemConfig:
    program_directory: str
    log_dir: str
    disable_can: bool
    debug: bool


@dataclass(frozen=True)
class CanConfig:
    interface: str
    channel: str
    bitrate: int
    fd: bool
    profile: str
    decoder: str
    receive_timeout: float


@dataclass(frozen=True)
class CacheConfig:
    stale_after_seconds: float
    default_door_state: str
    coalesce_by_frame: bool
    door_count: int
    min_interval_per_pgn_ms: int | None
    process_every_n_frames: int | None


@dataclass(frozen=True)
class TelemetryConfig:
    temperature_mode: str
    sim_target_inside: float
    sim_target_outside: float
    sim_tick_seconds: float
    sim_step_c: float
    sim_max_drift_c: float


@dataclass(frozen=True)
class AppConfig:
    api: ApiConfig
    system: SystemConfig
    can: CanConfig
    cache: CacheConfig
    telemetry: TelemetryConfig
    mapping: dict[str, Any]


def _profile_bitrate(profile: str, explicit_bitrate: int | None) -> int:
    if explicit_bitrate is not None and explicit_bitrate > 0:
        return int(explicit_bitrate)
    if profile.lower() in ("bus-fms", "bus_fms"):
        return 250_000
    return 500_000


def _pick(raw: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for k in keys:
        if k in raw:
            return raw[k]
    return default


def load_config(path: Path) -> AppConfig:
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")

    with open(path, "rb") as f:
        raw = tomllib.load(f)

    api = raw.get("API", {})
    sys_ = raw.get("System", {})
    can = raw.get("CAN", {})
    cache = raw.get("Cache", {})
    telem = raw.get("Telemetry", {})
    mapping = dict(raw.get("Mapping", {}))

    profile = str(_pick(can, "Profile", "profile", default="bus-fms"))
    bitrate_raw = _pick(can, "Bitrate", "bitrate")
    bitrate = _profile_bitrate(
        profile,
        int(bitrate_raw) if bitrate_raw is not None else None,
    )

    return AppConfig(
        api=ApiConfig(
            host=str(_pick(api, "Host", "host", default="0.0.0.0")),
            port=int(_pick(api, "HTTP_Port", "http-port", default=7080)),
            workers=int(_pick(api, "Workers", "workers", default=1)),
        ),
        system=SystemConfig(
            program_directory=str(
                _pick(
                    sys_,
                    "ProgramDirectory",
                    "program-directory",
                    default="/usr/local/can-telemetry",
                )
            ),
            log_dir=str(_pick(sys_, "LogDir", "log-dir", default="logs")),
            disable_can=bool(_pick(sys_, "DisableCan", "disable-can", default=False)),
            debug=bool(_pick(sys_, "Debug", "debug", default=False)),
        ),
        can=CanConfig(
            interface=str(_pick(can, "Interface", "interface", default="socketcan")),
            channel=str(_pick(can, "Channel", "channel", default="can0")),
            bitrate=bitrate,
            fd=bool(_pick(can, "FD", "fd", default=False)),
            profile=profile,
            decoder=str(_pick(can, "Decoder", "decoder", default="noop")),
            receive_timeout=float(
                _pick(can, "ReceiveTimeout", "receive-timeout", default=0.5)
            ),
        ),
        cache=CacheConfig(
            stale_after_seconds=float(
                _pick(cache, "StaleAfterSeconds", "stale-after-seconds", default=30.0)
            ),
            default_door_state=str(
                _pick(cache, "DefaultDoorState", "default-door-state", default="unknown")
            ),
            coalesce_by_frame=bool(
                _pick(cache, "CoalesceByFrame", "coalesce-by-frame", default=True)
            ),
            door_count=int(_pick(cache, "DoorCount", "door-count", default=4)),
            min_interval_per_pgn_ms=(
                int(_pick(cache, "MinIntervalPerPgnMs", "min-interval-per-pgn-ms"))
                if _pick(cache, "MinIntervalPerPgnMs", "min-interval-per-pgn-ms") is not None
                else None
            ),
            process_every_n_frames=(
                int(_pick(cache, "ProcessEveryNFrames", "process-every-n-frames"))
                if _pick(cache, "ProcessEveryNFrames", "process-every-n-frames") is not None
                else None
            ),
        ),
        telemetry=TelemetryConfig(
            temperature_mode=str(
                _pick(telem, "TemperatureMode", "temperature-mode", default="simulated")
            ).lower(),
            sim_target_inside=float(
                _pick(telem, "SimTargetInside", "sim-target-inside", default=22.0)
            ),
            sim_target_outside=float(
                _pick(telem, "SimTargetOutside", "sim-target-outside", default=15.0)
            ),
            sim_tick_seconds=float(
                _pick(telem, "SimTickSeconds", "sim-tick-seconds", default=5.0)
            ),
            sim_step_c=float(_pick(telem, "SimStepC", "sim-step-c", default=0.1)),
            sim_max_drift_c=float(
                _pick(telem, "SimMaxDriftC", "sim-max-drift-c", default=2.0)
            ),
        ),
        mapping=mapping,
    )
