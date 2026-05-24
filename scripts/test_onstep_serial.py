#!/usr/bin/env python3
"""CLI probe for OnStep LX200 serial protocol.

Tests park/unpark commands from a known parked state, then tests park
after a 5° RA slew to confirm whether :hP# blocks or is fire-and-forget.

Run on the Pi with the mount connected (mount must be PARKED first):

    python3 scripts/test_onstep_serial.py /dev/ttyUSB0
    python3 scripts/test_onstep_serial.py /dev/ttyUSB0 --baud 9600 --timeout 5.0

The script does NOT use any SmartTScope code — raw pyserial only.
"""

import argparse
import sys
import time

try:
    import serial
except ImportError:
    sys.exit("pyserial not installed: pip install pyserial")


# ── low-level helpers ─────────────────────────────────────────────────────────

def _send(ser: serial.Serial, cmd: str) -> None:
    ser.reset_input_buffer()
    ser.write(cmd.encode())


def _read_until_hash_or_timeout(ser: serial.Serial, timeout_s: float) -> tuple[bytes, float]:
    """Read until '#' terminator or timeout. Returns (data, elapsed_s)."""
    buf = b""
    t0 = time.monotonic()
    deadline = t0 + timeout_s
    while time.monotonic() < deadline:
        chunk = ser.read(ser.in_waiting or 1)
        if chunk:
            buf += chunk
            if b"#" in buf:
                break
    return buf, time.monotonic() - t0


def _read_single_byte(ser: serial.Serial, timeout_s: float) -> tuple[bytes, float]:
    """Read exactly 1 byte within timeout_s. Returns (byte_or_empty, elapsed_s)."""
    t0 = time.monotonic()
    deadline = t0 + timeout_s
    while time.monotonic() < deadline:
        b = ser.read(1)
        if b:
            return b, time.monotonic() - t0
    return b"", time.monotonic() - t0


def _probe_single(ser: serial.Serial, cmd: str, label: str, timeout_s: float) -> bytes:
    """Send cmd, try to read a single-byte reply. Print results."""
    print(f"\n{'─'*60}")
    print(f"  CMD : {cmd!r}  ({label})")
    _send(ser, cmd)
    data, elapsed = _read_single_byte(ser, timeout_s)
    if data:
        print(f"  RAW : {data!r}  HEX: {data.hex(' ')}")
        print(f"  BYTE: 0x{data[0]:02x} = {chr(data[0])!r}")
        print(f"  TIME: {elapsed*1000:.1f} ms  ← response latency")
        # drain any remaining bytes (e.g. leftover '#')
        time.sleep(0.05)
        leftover = ser.read(ser.in_waiting)
        if leftover:
            print(f"  LEFTOVER IN BUFFER: {leftover!r}")
    else:
        print(f"  RAW : (no response within {timeout_s*1000:.0f} ms timeout)")
        print(f"  TIME: {elapsed*1000:.1f} ms")
    return data


def _gu(ser: serial.Serial, label: str = "") -> str:
    """Send :GU# and return decoded status string."""
    _send(ser, ":GU#")
    data, elapsed = _read_until_hash_or_timeout(ser, timeout_s=1.0)
    decoded = data.rstrip(b"#").decode(errors="replace") if data else "(none)"
    tag = f"  [{label}]" if label else ""
    print(f"  :GU#{tag} → {data!r}  decoded={decoded!r}  ({elapsed*1000:.1f} ms)")
    return decoded


def _get_ra(ser: serial.Serial) -> str:
    """Return current RA as HH:MM:SS string."""
    _send(ser, ":GR#")
    data, _ = _read_until_hash_or_timeout(ser, timeout_s=1.0)
    return data.rstrip(b"#").decode(errors="replace").strip()


def _get_dec(ser: serial.Serial) -> str:
    """Return current Dec as sDD*MM'SS or sDD*MM:SS string."""
    _send(ser, ":GD#")
    data, _ = _read_until_hash_or_timeout(ser, timeout_s=1.0)
    return data.rstrip(b"#").decode(errors="replace").strip()


def _add_20min_ra(ra_str: str) -> str:
    """Add 20 minutes (= 5°) to an HH:MM:SS RA string. Wraps at 24 h."""
    parts = ra_str.split(":")
    h, m, s = int(parts[0]), int(parts[1]), int(float(parts[2]))
    total_s = h * 3600 + m * 60 + s + 20 * 60
    total_s %= 24 * 3600
    hh = total_s // 3600
    mm = (total_s % 3600) // 60
    ss = total_s % 60
    return f"{hh:02d}:{mm:02d}:{ss:02d}"


def _wait_slew_done(ser: serial.Serial, timeout_s: float = 120.0) -> bool:
    """Poll :D# until no '|' (slew done) or timeout."""
    print(f"  Waiting for slew to finish (up to {timeout_s:.0f} s)…", end="", flush=True)
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        _send(ser, ":D#")
        data, _ = _read_until_hash_or_timeout(ser, timeout_s=0.5)
        if b"|" not in data and b"\x7f" not in data:
            print(" done.")
            return True
        print(".", end="", flush=True)
        time.sleep(1.0)
    print(" TIMEOUT.")
    return False


def _header(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="OnStep LX200 serial protocol probe")
    ap.add_argument("port", help="Serial port, e.g. /dev/ttyUSB0")
    ap.add_argument("--baud",    type=int,   default=9600)
    ap.add_argument("--timeout", type=float, default=5.0,
                    help="Read timeout for single-byte replies in seconds (default 5.0)")
    args = ap.parse_args()

    print(f"Opening {args.port} @ {args.baud} baud  (single-byte timeout {args.timeout} s)")
    try:
        ser = serial.Serial(args.port, args.baud, timeout=args.timeout)
    except (serial.SerialException, OSError) as exc:
        sys.exit(f"Cannot open port: {exc}")
    time.sleep(0.5)

    # ── Step 0: firmware handshake ───────────────────────────────────────────
    _header("STEP 0 — firmware handshake :GVP#")
    _send(ser, ":GVP#")
    data, elapsed = _read_until_hash_or_timeout(ser, timeout_s=3.0)
    print(f"  :GVP# → {data!r}  ({elapsed*1000:.1f} ms)")

    # ── Step 1: confirm parked ───────────────────────────────────────────────
    _header("STEP 1 — initial state (mount should be PARKED)")
    status = _gu(ser, "initial")
    if not status.startswith("P"):
        print(f"\n  WARNING: first :GU# char is {status[0]!r}, not 'P'.")
        print("  Mount may not be parked — results may differ from expected.")
    else:
        print("  OK: mount reports PARKED (first char = 'P')")

    # ── Step 2: unpark with :hR# (correct command) ──────────────────────────
    _header("STEP 2 — UNPARK with :hR# (spec command, from PARKED state)")
    print(f"  Note: previous run showed ~2 s latency — using {args.timeout} s timeout")
    resp_hR = _probe_single(ser, ":hR#", "Restore/unpark", timeout_s=args.timeout)
    print("\n  :GU# immediately after :hR#:")
    _gu(ser, "after :hR#")
    time.sleep(1.0)
    _gu(ser, "1 s later")

    # ── Step 3: re-park (to reset state for :hU# test) ──────────────────────
    _header("STEP 3 — re-PARK before testing :hU#")
    print("  (slewing back to park position so :hU# test starts from PARKED)")
    resp_park1 = _probe_single(ser, ":hP#", "Park", timeout_s=args.timeout)
    print("\n  Waiting for park to complete…")
    for i in range(30):
        time.sleep(2.0)
        gu = _gu(ser, f"poll {i+1}")
        if gu.startswith("P"):
            print("  Mount is PARKED.")
            break
    else:
        print("  WARNING: mount did not report PARKED within 60 s")

    # ── Step 4: unpark with :hU# (wrong command, for comparison) ────────────
    _header("STEP 4 — UNPARK with :hU# (current code, from PARKED state)")
    resp_hU = _probe_single(ser, ":hU#", "Unpark (current code)", timeout_s=args.timeout)
    print("\n  :GU# immediately after :hU#:")
    _gu(ser, "after :hU#")
    time.sleep(1.0)
    _gu(ser, "1 s later")

    # ── Step 5: slew 5° in RA then test park timing ──────────────────────────
    _header("STEP 5 — slew 5° in RA (20 min), then test :hP# timing")

    # 5a: make sure we're unparked (use :hR# since it works)
    print("  Ensuring mount is unparked before slew…")
    gu_now = _gu(ser, "before unpark-for-slew")
    if gu_now.startswith("P"):
        print("  Sending :hR# to unpark…")
        _probe_single(ser, ":hR#", "unpark for slew", timeout_s=args.timeout)
        time.sleep(0.5)
        _gu(ser, "after unpark")

    # 5b: read current RA/Dec and build a target 20 min east
    ra_now  = _get_ra(ser)
    dec_now = _get_dec(ser)
    ra_target = _add_20min_ra(ra_now)
    print(f"\n  Current  RA={ra_now}  Dec={dec_now}")
    print(f"  Target   RA={ra_target}  Dec={dec_now}  (+20 min RA = +5°)")

    # 5c: set target and slew
    _send(ser, f":Sr{ra_target}#")
    r1, _ = _read_single_byte(ser, timeout_s=1.0)
    _send(ser, f":Sd{dec_now}#")
    r2, _ = _read_single_byte(ser, timeout_s=1.0)
    print(f"  :Sr reply={r1!r}  :Sd reply={r2!r}")

    _send(ser, ":MS#")
    r3, el3 = _read_single_byte(ser, timeout_s=2.0)
    print(f"  :MS# reply={r3!r}  ({el3*1000:.1f} ms)  [0=ok, else error code]")

    if r3 != b"0":
        print(f"  WARNING: GoTo rejected (code {r3!r}) — skipping park timing test")
    else:
        _wait_slew_done(ser, timeout_s=120.0)
        _gu(ser, "after slew")

        # 5d: issue :hP# and measure — does it block until park position reached?
        _header("STEP 5d — :hP# timing after 5° slew away from park")
        print(f"  If :hP# blocks until physically parked → response time ≈ slew time (30–120 s)")
        print(f"  If :hP# is fire-and-forget             → response time ≈ 0–2 s")
        t_park_start = time.monotonic()
        resp_park2 = _probe_single(ser, ":hP#", "Park after slew", timeout_s=120.0)
        t_park_resp = time.monotonic() - t_park_start
        print(f"\n  Total time from :hP# send to byte received: {t_park_resp:.1f} s")

        print("\n  Polling :GU# every 2 s to find when PARKED state appears…")
        for i in range(60):
            time.sleep(2.0)
            gu = _gu(ser, f"poll {i+1} ({(i+1)*2} s after :hP# reply)")
            if gu.startswith("P"):
                print(f"  Mount PARKED at t+{(i+1)*2 + t_park_resp:.0f} s from :hP# send")
                break
        else:
            print("  WARNING: mount did not report PARKED within 120 s of :hP# reply")

    # ── Summary ──────────────────────────────────────────────────────────────
    _header("SUMMARY")
    print(f"  :hR# reply: {resp_hR!r}  ({'1=success' if resp_hR == b'1' else '0=fail or no response'})")
    print(f"  :hU# reply: {resp_hU!r}  ({'1=success' if resp_hU == b'1' else '0=fail or no response'})")
    print(f"  :hP# reply during step 3: {resp_park1!r}")

    ser.close()
    print("\nPort closed.  Done.")


if __name__ == "__main__":
    main()
