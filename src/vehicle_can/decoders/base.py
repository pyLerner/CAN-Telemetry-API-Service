from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    import can

    from telemetry.cache import TelemetryCache


@runtime_checkable
class CanTelemetryDecoder(Protocol):
    """Decode one CAN frame into telemetry cache (sync; caller holds cache.lock)."""

    def configure(self, mapping: dict) -> None:
        ...

    def decode_frame(self, msg: can.Message, cache: TelemetryCache) -> None:
        ...


def j1939_pgn_from_id(arbitration_id: int) -> int:
    """Extract 18-bit PGN from 29-bit J1939 extended CAN ID."""
    return (arbitration_id >> 8) & 0x3FFFF
