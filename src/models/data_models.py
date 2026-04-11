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

    profile = str(can.get("Profile", "bus-fms"))
    bitrate_raw = can.get("Bitrate")
    bitrate = _profile_bitrate(
        profile,
        int(bitrate_raw) if bitrate_raw is not None else None,
    )

    return AppConfig(
        api=ApiConfig(
            host=str(api.get("Host", "0.0.0.0")),
            port=int(api.get("HTTP_Port", 7080)),
            workers=int(api.get("Workers", 1)),
        ),
        system=SystemConfig(
            program_directory=str(sys_.get("ProgramDirectory", "/usr/local/can-telemetry")),
            log_dir=str(sys_.get("LogDir", "logs")),
            disable_can=bool(sys_.get("DisableCan", False)),
        ),
        can=CanConfig(
            interface=str(can.get("Interface", "socketcan")),
            channel=str(can.get("Channel", "can0")),
            bitrate=bitrate,
            fd=bool(can.get("FD", False)),
            profile=profile,
            decoder=str(can.get("Decoder", "noop")),
            receive_timeout=float(can.get("ReceiveTimeout", 0.5)),
        ),
        cache=CacheConfig(
            stale_after_seconds=float(cache.get("StaleAfterSeconds", 30.0)),
            default_door_state=str(cache.get("DefaultDoorState", "unknown")),
            coalesce_by_frame=bool(cache.get("CoalesceByFrame", True)),
            door_count=int(cache.get("DoorCount", 4)),
            min_interval_per_pgn_ms=(
                int(cache["MinIntervalPerPgnMs"])
                if cache.get("MinIntervalPerPgnMs") is not None
                else None
            ),
            process_every_n_frames=(
                int(cache["ProcessEveryNFrames"])
                if cache.get("ProcessEveryNFrames") is not None
                else None
            ),
        ),
        telemetry=TelemetryConfig(
            temperature_mode=str(telem.get("TemperatureMode", "simulated")).lower(),
            sim_target_inside=float(telem.get("SimTargetInside", 22.0)),
            sim_target_outside=float(telem.get("SimTargetOutside", 15.0)),
            sim_tick_seconds=float(telem.get("SimTickSeconds", 5.0)),
            sim_step_c=float(telem.get("SimStepC", 0.1)),
            sim_max_drift_c=float(telem.get("SimMaxDriftC", 2.0)),
        ),
        mapping=mapping,
    )
