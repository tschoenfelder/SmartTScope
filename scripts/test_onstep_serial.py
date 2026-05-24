#!/usr/bin/env python3
"""CLI probe for OnStep LX200 serial protocol.

Sends park/unpark/status commands and measures exact response bytes and timing.
Run on the Pi with the mount connected:

    python3 scripts/test_onstep_serial.py /dev/ttyUSB0
    python3 scripts/test_onstep_serial.py /dev/ttyUSB0 --baud 9600

The script does NOT use any SmartTScope code — raw pyserial only.
"""

import argparse
import sys
import time

try:
    import serial
except ImportError:
    sys.exit("pyserial not installed: pip install pyserial")


# ── helpers ───────────────────────────────────────────────────────────────────

def _send_raw(ser: serial.Serial, cmd: str) -> None:
    ser.reset_input_buffer()
    ser.write(cmd.encode())


def _read_timed(ser: serial.Serial, max_bytes: int = 32, timeout_s: float = 1.0) -> tuple[bytes, float]:
    """Read up to max_bytes for up to timeout_s seconds.

    Returns (data_received, elapsed_seconds).
    Stops early on '#' terminator or when no more bytes arrive.
    """
    buf = b""
    t0 = time.monotonic()
    deadline = t0 + timeout_s
    while time.monotonic() < deadline:
        chunk = ser.read(max(1, ser.in_waiting or 1))
        if chunk:
            buf += chunk
            if b"#" in buf:
                break
            if len(buf) >= max_bytes:
                break
        elif buf:
            # Data stopped arriving — give it 20 ms more then quit
            time.sleep(0.02)
            chunk = ser.read(ser.in_waiting or 1)
            buf += chunk
            break
    return buf, time.monotonic() - t0


def _probe(ser: serial.Serial, cmd: str, label: str, timeout_s: float = 1.0) -> None:
    print(f"\n{'─'*60}")
    print(f"  CMD : {cmd!r}  ({label})")
    _send_raw(ser, cmd)
    data, elapsed = _read_timed(ser, timeout_s=timeout_s)
    if data:
        print(f"  RAW : {data!r}")
        print(f"  HEX : {data.hex(' ')}")
        print(f"  TIME: {elapsed*1000:.1f} ms")
        if len(data) == 1:
            print(f"  BYTE: 0x{data[0]:02x} = {chr(data[0])!r}  (single-byte reply)")
    else:
        print(f"  RAW : (no response within {timeout_s*1000:.0f} ms)")
        print(f"  TIME: {elapsed*1000:.1f} ms (timeout)")


def _status(ser: serial.Serial) -> str:
    ser.reset_input_buffer()
    ser.write(b":GU#")
    data, elapsed = _read_timed(ser, timeout_s=0.5)
    decoded = data.rstrip(b"#").decode(errors="replace") if data else "(none)"
    print(f"\n  :GU# → {data!r}  decoded={decoded!r}  ({elapsed*1000:.1f} ms)")
    return decoded


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="OnStep LX200 serial protocol probe")
    ap.add_argument("port", help="Serial port, e.g. /dev/ttyUSB0")
    ap.add_argument("--baud", type=int, default=9600)
    ap.add_argument("--timeout", type=float, default=1.0,
                    help="Serial read timeout in seconds (default 1.0)")
    args = ap.parse_args()

    print(f"Opening {args.port} @ {args.baud} baud  (read timeout {args.timeout} s)")
    try:
        ser = serial.Serial(args.port, args.baud, timeout=args.timeout)
    except (serial.SerialException, OSError) as exc:
        sys.exit(f"Cannot open port: {exc}")

    time.sleep(0.5)  # let the port settle

    print("\n" + "="*60)
    print("  STEP 1 — firmware handshake :GVP#")
    print("="*60)
    _probe(ser, ":GVP#", "Get firmware name", timeout_s=2.0)

    print("\n" + "="*60)
    print("  STEP 2 — initial status :GU#")
    print("="*60)
    status_before = _status(ser)

    print("\n" + "="*60)
    print("  STEP 3 — UNPARK  :hR#  (spec: reply 0 or 1, no # terminator)")
    print("            also testing :hU# for comparison")
    print("="*60)
    _probe(ser, ":hR#", "Restore / unpark (spec command)", timeout_s=args.timeout)
    time.sleep(0.3)
    print("\n  Status immediately after :hR#:")
    _status(ser)

    print("\n  Now trying :hU# (current code uses this):")
    _probe(ser, ":hU#", "Unpark (current code)", timeout_s=args.timeout)
    time.sleep(0.3)
    print("\n  Status immediately after :hU#:")
    _status(ser)

    time.sleep(1.0)
    print("\n  Status 1 s after unpark commands:")
    _status(ser)

    print("\n" + "="*60)
    print("  STEP 4 — PARK  :hP#  (spec: reply 0 or 1, no # terminator)")
    print("="*60)
    _probe(ser, ":hP#", "Move to park position", timeout_s=args.timeout)
    time.sleep(0.3)
    print("\n  Status immediately after :hP#:")
    _status(ser)

    time.sleep(3.0)
    print("\n  Status 3 s after :hP# (slew may be in progress):")
    _status(ser)

    print("\n" + "="*60)
    print("  STEP 5 — :D# slew indicator (| chars = slewing, else empty)")
    print("="*60)
    _probe(ser, ":D#", "Distance bars", timeout_s=0.5)

    ser.close()
    print(f"\nPort closed.  Done.")


if __name__ == "__main__":
    main()
