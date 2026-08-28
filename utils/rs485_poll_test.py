#!/usr/bin/env python3
"""RS-485 text-protocol poll test for H-3568 stand (master 1A00, slaves 1A01/1A02)."""

from __future__ import annotations

import argparse
import re
import sys
import time
from datetime import datetime

import serial
import serial.rs485

DEFAULT_PORT = "/dev/ttyS9"
DEFAULT_BAUDRATE = 19200
DEFAULT_INTERVAL = 1.0
DEFAULT_TIMEOUT = 0.5
DEFAULT_DEVICES = ("1A01", "1A02")

RESPONSE_RE = re.compile(r"^\{([0-9A-Fa-f]{4});([0-9A-Fa-f]{6})\}$")
RESPONSE_SEARCH_RE = re.compile(r"\{[0-9A-Fa-f]{4};[0-9A-Fa-f]{6}\}")
DOOR_LABELS = {"00": "close", "FF": "open"}


def ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def make_request(device_id: str) -> bytes:
    request = f"{{{device_id.upper()}}}"
    if len(request) != 6:
        raise ValueError(f"Request must be 6 chars, got {len(request)}: {request!r}")
    return request.encode("ascii")


def decode_doors(door_hex: str) -> list[str]:
    if len(door_hex) != 6:
        raise ValueError(f"Expected 6 hex chars for 3 doors, got {door_hex!r}")
    return [DOOR_LABELS.get(door_hex[i : i + 2].upper(), door_hex[i : i + 2]) for i in range(0, 6, 2)]


def open_port(port: str, baudrate: int, timeout: float) -> serial.rs485.RS485:
    ser = serial.rs485.RS485(
        port=port,
        baudrate=baudrate,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=timeout,
    )
    ser.rs485_mode = serial.rs485.RS485Settings(
        rts_level_for_tx=True,
        rts_level_for_rx=False,
        delay_before_tx=0.001,
        delay_before_rx=0.003,
    )
    return ser


def read_response(ser: serial.rs485.RS485, timeout: float) -> bytes:
    deadline = time.monotonic() + timeout
    buffer = bytearray()

    while time.monotonic() < deadline:
        chunk = ser.read(ser.in_waiting or 1)
        if chunk:
            buffer.extend(chunk)
            text = buffer.decode("ascii", errors="replace")
            match = RESPONSE_SEARCH_RE.search(text)
            if match:
                return match.group(0).encode("ascii")
        else:
            time.sleep(0.005)

    return b""


def parse_response(raw: bytes) -> tuple[str, str, list[str]]:
    text = raw.decode("ascii", errors="replace").strip()
    match = RESPONSE_RE.match(text)
    if not match:
        raise ValueError(f"Invalid response: {text!r}")
    addr, doors_hex = match.group(1).upper(), match.group(2).upper()
    return addr, doors_hex, decode_doors(doors_hex)


def poll_device(ser: serial.rs485.RS485, device_id: str, timeout: float) -> None:
    request = make_request(device_id)
    print(f"{ts()} TX -> {request.decode('ascii')}")

    ser.reset_input_buffer()
    ser.write(request)
    ser.flush()

    raw = read_response(ser, timeout)
    if not raw:
        print(f"{ts()} RX <- (timeout, no valid response)")
        return

    text = raw.decode("ascii", errors="replace")
    print(f"{ts()} RX <- {text}")

    try:
        addr, doors_hex, doors = parse_response(raw)
        print(f"{ts()}     addr={addr} doors_hex={doors_hex} doors={doors}")
    except ValueError as exc:
        print(f"{ts()}     parse error: {exc}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Poll RS-485 door devices on H-3568 stand.")
    parser.add_argument("--port", default=DEFAULT_PORT, help=f"Serial port (default: {DEFAULT_PORT})")
    parser.add_argument("--baudrate", type=int, default=DEFAULT_BAUDRATE, help=f"Baud rate (default: {DEFAULT_BAUDRATE})")
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL, help=f"Poll interval in seconds (default: {DEFAULT_INTERVAL})")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help=f"Response timeout in seconds (default: {DEFAULT_TIMEOUT})")
    parser.add_argument(
        "--devices",
        default=",".join(DEFAULT_DEVICES),
        help=f"Comma-separated device IDs (default: {','.join(DEFAULT_DEVICES)})",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    devices = [d.strip().upper() for d in args.devices.split(",") if d.strip()]
    if not devices:
        print("No devices specified.", file=sys.stderr)
        return 1

    print(
        f"RS-485 poll test: port={args.port} baud={args.baudrate} "
        f"devices={devices} interval={args.interval}s timeout={args.timeout}s"
    )

    ser = open_port(args.port, args.baudrate, args.timeout)
    try:
        while True:
            for device_id in devices:
                poll_device(ser, device_id, args.timeout)
            print(f"--- cycle done, next in {args.interval}s ---")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nStopped.")
        return 0
    finally:
        ser.close()


if __name__ == "__main__":
    raise SystemExit(main())
