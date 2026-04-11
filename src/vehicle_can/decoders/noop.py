from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from telemetry.cache import TelemetryCache


class NoopDecoder:
    def configure(self, mapping: dict[str, Any]) -> None:
        pass

    def decode_frame(self, msg: object, cache: TelemetryCache) -> None:
        del msg, cache
