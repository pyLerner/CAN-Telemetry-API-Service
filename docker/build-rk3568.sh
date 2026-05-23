#!/usr/bin/env bash
set -euo pipefail

# RK3568 / Ubuntu 20.04 friendly build path:
# disable BuildKit/buildx and use classic docker builder.
export DOCKER_BUILDKIT=0
export COMPOSE_DOCKER_CLI_BUILD=0

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${PROJECT_ROOT}"

VERSION="$(
    python3 - <<'PY'
import pathlib
import tomllib

data = tomllib.loads(pathlib.Path("pyproject.toml").read_text(encoding="utf-8"))
print(data["project"]["version"])
PY
)"
docker build --no-cache -f docker/Dockerfile -t "can-telemetry-api:${VERSION}" .

echo "Built can-telemetry-api:${VERSION}"
