from __future__ import annotations

import importlib
from typing import Any, Type

from models.data_models import AppConfig

from vehicle_can.decoders.base import CanTelemetryDecoder
from vehicle_can.decoders.bus_fms import BusFmsDecoder
from vehicle_can.decoders.dbc_generic import DbcGenericDecoder
from vehicle_can.decoders.noop import NoopDecoder
from vehicle_can.decoders.t856 import T856Decoder

BUILTIN_DECODERS: dict[str, Type[CanTelemetryDecoder]] = {
    "noop": NoopDecoder,
    "bus-fms": BusFmsDecoder,
    "bus_fms": BusFmsDecoder,
    "dbc": DbcGenericDecoder,
    "dbc-generic": DbcGenericDecoder,
    "t856": T856Decoder,
}


def load_decoder_class(name_or_fqn: str) -> Type[CanTelemetryDecoder]:
    s = name_or_fqn.strip()
    if ":" in s:
        mod_name, _, cls_name = s.partition(":")
        mod = importlib.import_module(mod_name)
        cls = getattr(mod, cls_name)
        if not isinstance(cls, type):
            raise TypeError(f"Not a class: {s}")
        return cls  # type: ignore[return-value]
    key = s.lower()
    if key not in BUILTIN_DECODERS:
        raise KeyError(
            f"Unknown decoder '{name_or_fqn}'. Built-in: {sorted(BUILTIN_DECODERS)}"
        )
    return BUILTIN_DECODERS[key]


def build_decoder(cfg: AppConfig) -> CanTelemetryDecoder:
    cls = load_decoder_class(cfg.can.decoder)
    dec: Any = cls()
    mapping = dict(cfg.mapping)
    system_cfg = dict(mapping.get("_system", {}))
    system_cfg["debug"] = cfg.system.debug
    mapping["_system"] = system_cfg
    dec.configure(mapping)
    return dec  # type: ignore[return-value]
