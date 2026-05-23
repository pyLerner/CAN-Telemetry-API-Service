#!/bin/sh
set -eu

CAN_IFACE="${CAN_IFACE:-can0}"
CAN_WAIT_SECONDS="${CAN_WAIT_SECONDS:-30}"

wait_for_can() {
    elapsed=0
    while [ "$elapsed" -lt "$CAN_WAIT_SECONDS" ]; do
        if ip link show "$CAN_IFACE" 2>/dev/null | grep -q "state UP"; then
            echo "$(date -u +"%Y-%m-%dT%H:%M:%SZ") CAN interface '${CAN_IFACE}' is UP, starting app"
            return 0
        fi
        if ip link show "$CAN_IFACE" 2>/dev/null | grep -q "<.*,UP,.*>"; then
            echo "$(date -u +"%Y-%m-%dT%H:%M:%SZ") CAN interface '${CAN_IFACE}' is UP, starting app"
            return 0
        fi
        sleep 1
        elapsed=$((elapsed + 1))
    done
    echo "$(date -u +"%Y-%m-%dT%H:%M:%SZ") ERROR: CAN interface '${CAN_IFACE}' not UP within ${CAN_WAIT_SECONDS}s" >&2
    return 1
}

echo "$(date -u +"%Y-%m-%dT%H:%M:%SZ") waiting for host-managed CAN interface '${CAN_IFACE}' (timeout ${CAN_WAIT_SECONDS}s)"
wait_for_can
exec "$@"
