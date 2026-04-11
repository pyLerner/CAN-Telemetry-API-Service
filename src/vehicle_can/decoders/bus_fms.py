from __future__ import annotations

from vehicle_can.decoders.dbc_generic import DbcGenericDecoder


class BusFmsDecoder(DbcGenericDecoder):
    """Bus-FMS / FMS-Standard stacks are typically expressed as J1939 DBC; same as DbcGeneric."""

    pass
