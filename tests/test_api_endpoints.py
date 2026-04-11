from __future__ import annotations

import sys
from pathlib import Path

_proj_root = Path(__file__).resolve().parents[1]
_src_dir = _proj_root / "src"
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from datetime import datetime

from starlette.testclient import TestClient


def test_get_api_ping_ok(client: TestClient) -> None:
    r = client.get("/api/ping")
    assert r.status_code == 200
    data = r.json()
    assert data["running"] == "ok"
    assert "timestamp" in data
    datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))


def test_doors_unknown_when_never_updated(client: TestClient) -> None:
    r = client.get("/api/telemetry/v1/doors/state")
    assert r.status_code == 200
    doors = r.json()["doors"]
    assert doors["1"] == "unknown"
    assert doors["2"] == "unknown"


def test_doors_seeded(client_seeded: TestClient) -> None:
    r = client_seeded.get("/api/telemetry/v1/doors/state")
    assert r.status_code == 200
    doors = r.json()["doors"]
    assert doors["1"] == "close"
    assert doors["2"] == "open"


def test_gear_state(client_seeded: TestClient) -> None:
    r = client_seeded.get("/api/telemetry/v1/gear/state")
    assert r.status_code == 200
    assert r.json()["reverse"] is False


def test_temperature_state_simulated(client: TestClient) -> None:
    r = client.get("/api/telemetry/v1/temperature/state")
    assert r.status_code == 200
    t = r.json()["temperatures"]
    assert "inside" in t and "outside" in t
    assert isinstance(t["inside"], (int, float))


def test_kebab_case_nested(client: TestClient) -> None:
    """If nested keys used underscores, they become kebab-case."""
    r = client.get("/api/ping")
    assert r.status_code == 200
    body = r.json()
    assert not any("_" in k for k in body.keys())


if __name__ == "__main__":
    import subprocess

    raise SystemExit(
        subprocess.call([sys.executable, "-m", "pytest", __file__, *sys.argv[1:]])
    )
