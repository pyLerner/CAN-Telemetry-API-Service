from __future__ import annotations

from pathlib import Path

from models.data_models import load_config


def test_load_example_config() -> None:
    root = Path(__file__).resolve().parents[1]
    cfg = load_config(root / "etc" / "telemetry-provider.toml")
    assert cfg.api.port == 7080
    assert cfg.can.bitrate == 250_000
    assert cfg.can.decoder == "noop"
    assert cfg.telemetry.temperature_mode == "simulated"
