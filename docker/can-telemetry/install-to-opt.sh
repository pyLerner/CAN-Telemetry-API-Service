#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo $0"
  exit 1
fi

BUNDLE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="/opt/can-telemetry"
OWNER_UID=1000
OWNER_GID=1000

install -d -m 0755 "${DEST}"
install -d -m 0755 "${DEST}/etc" "${DEST}/logs" "${DEST}/data"

if [[ -d "${BUNDLE_DIR}/etc" ]]; then
  cp -a "${BUNDLE_DIR}/etc/." "${DEST}/etc/"
fi
if [[ -d "${BUNDLE_DIR}/logs" ]]; then
  cp -a "${BUNDLE_DIR}/logs/." "${DEST}/logs/"
fi
if [[ -d "${BUNDLE_DIR}/data" ]]; then
  cp -a "${BUNDLE_DIR}/data/." "${DEST}/data/"
fi

chown -R "${OWNER_UID}:${OWNER_GID}" "${DEST}"

echo "Installed bundle to ${DEST} (owner ${OWNER_UID}:${OWNER_GID})"
echo "  etc:  ${DEST}/etc"
echo "  logs: ${DEST}/logs"
echo "  data: ${DEST}/data"
