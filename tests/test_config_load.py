from __future__ import annotations

import sys
from pathlib import Path

_proj_root = Path(__file__).resolve().parents[1]
_src_dir = _proj_root / "src"
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from models.data_models import load_config


def test_load_example_config() -> None:
    root = Path(__file__).resolve().parents[1]
    cfg = load_config(root / "etc" / "telemetry-provider.toml")
    assert cfg.api.port == 7080
    assert cfg.can.bitrate == 250_000
    assert cfg.can.decoder == "t856"
    assert cfg.telemetry.temperature_mode == "can"
    assert cfg.system.debug is False
    assert cfg.mapping["temperature"]["queue-len"] == 5


if __name__ == "__main__":
    import subprocess

    raise SystemExit(
        subprocess.call([sys.executable, "-m", "pytest", __file__, *sys.argv[1:]])
    )
