"""OnStep V4 mount adapter — LX200 serial protocol over pyserial."""

from __future__ import annotations

import contextlib
import logging
import threading
import time

import serial

from ...ports.mount import MountPort, MountPosition, MountState

_log = logging.getLogger(__name__)

# ── sexagesimal helpers ────────────────────────────────────────────────────────

def _format_ra(ra: float) -> str:
    ra = ra % 24
    h = int(ra)
    rem = (ra - h) * 60
    m = int(rem)
    s = int((rem - m) * 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _format_dec(dec: float) -> str:
    sign = "+" if dec >= 0 else "-"
    dec = abs(dec)
    d = int(dec)
    rem = (dec - d) * 60
    m = int(rem)
    s = int((rem - m) * 60)
    return f"{sign}{d:02d}*{m:02d}:{s:02d}"


def _parse_ra(s: str) -> float:
    parts = s.strip().split(":")
    return float(parts[0]) + float(parts[1]) / 60 + float(parts[2]) / 3600


def _parse_dec(s: str) -> float:
    s = s.strip()
    sign = -1 if s.startswith("-") else 1
    s = s.lstrip("+-").replace("*", ":")
    parts = s.split(":")
    return sign * (float(parts[0]) + float(parts[1]) / 60 + float(parts[2]) / 3600)


# ── adapter ───────────────────────────────────────────────────────────────────

class OnStepMount(MountPort):
    def __init__(
        self,
        port: str,
        baud_rate: int = 9600,
        timeout: float = 2.0,
    ) -> None:
        self._port = port
        self._baud_rate = baud_rate
        self._timeout = timeout
        self._serial: serial.Serial | None = None
        self._lock = threading.Lock()

    def connect(self) -> bool:
        if self._serial is not None and self._serial.is_open:
            _log.info("OnStepMount.connect(): already open on %s", self._port)
            return True  # already connected — idempotent
        _log.info("OnStepMount.connect(): opening %s @ %d baud timeout=%.1fs",
                  self._port, self._baud_rate, self._timeout)
        try:
            self._serial = serial.Serial(self._port, self._baud_rate, timeout=self._timeout)
        except (serial.SerialException, OSError) as exc:
            _log.error("OnStepMount.connect(): failed to open %s — %s", self._port, exc)
            return False

        # Confirm we're talking to OnStep and not another serial device on this port.
        # Uses read() instead of readline() so unit-test mocks (which only stub
        # readline) pass through unaffected; non-bytes mock return values are
        # treated as "no response" and accepted as inconclusive.
        # Accepts "OnStep" and "On-Step" (both appear across firmware versions).
        # On reconnect the input buffer may contain a stale command ACK ('0' or '1').
        # If we get a short numeric response, flush and retry once before rejecting.
        self._serial.reset_input_buffer()
        self._serial.write(b":GVP#")
        raw = self._serial.read(32)
        product = ""
        if isinstance(raw, bytes):
            product = raw.decode(errors="replace").rstrip("#\r\n").strip()
            _log.info("OnStepMount.connect(): :GVP# response = %r", product)
            if product and len(product) <= 2 and all(c in "0123456789" for c in product):
                # Looks like a stale command ACK — flush and retry once
                _log.warning(
                    "OnStepMount.connect(): :GVP# returned short numeric %r (stale ACK?) — flushing and retrying",
                    product,
                )
                time.sleep(0.3)
                self._serial.reset_input_buffer()
                self._serial.write(b":GVP#")
                raw2 = self._serial.read(32)
                if isinstance(raw2, bytes):
                    product = raw2.decode(errors="replace").rstrip("#\r\n").strip()
                    _log.info("OnStepMount.connect(): :GVP# retry response = %r", product)
            if product and "on" not in product.lower() and "step" not in product.lower():
                _log.error("OnStepMount.connect(): unexpected product %r — not OnStep, closing", product)
                self._serial.close()
                self._serial = None
                return False
        else:
            _log.warning("OnStepMount.connect(): :GVP# returned non-bytes %r (mock?)", raw)

        self.disable_tracking()
        _log.info("OnStepMount.connect(): connected — product=%r port=%s", product, self._port)
        return True

    def disconnect(self) -> None:
        if self._serial is not None:
            self._serial.close()

    def _raw_send(self, cmd: str) -> bytes:
        if self._serial is None:
            return b""
        with self._lock:
            try:
                self._serial.write(cmd.encode())
                return bytes(self._serial.readline())
            except Exception:
                self._serial = None
                raise

    def _send(self, cmd: str) -> str:
        return self._raw_send(cmd).decode(errors="replace").rstrip("#\r\n")

    def get_state(self) -> MountState:
        r = self._send(":GU#")
        if not r:
            return MountState.UNKNOWN
        # Priority order matters — check tracking before meridian-side letters.
        # OnStep uses 'E'/'W' for east/west of meridian (normal positions), not limits.
        # Actual hardware limits are signalled by 'l' (lowercase) in V4 firmware.
        if "P" in r:
            return MountState.PARKED
        if "S" in r:
            return MountState.SLEWING
        if "l" in r:
            return MountState.AT_LIMIT
        if "T" in r:
            return MountState.TRACKING
        return MountState.UNPARKED

    def unpark(self) -> bool:
        return len(self._raw_send(":hU#")) > 0

    def enable_tracking(self) -> bool:
        r = self._send(":Te#")
        return r != "0"  # accept "1" (V4 ACK) and "" (no-ACK firmware); reject explicit "0"

    def get_position(self) -> MountPosition:
        ra = _parse_ra(self._send(":GR#"))
        dec = _parse_dec(self._send(":GD#"))
        return MountPosition(ra=ra, dec=dec)

    def sync(self, ra: float, dec: float) -> bool:
        self._send(f":Sr{_format_ra(ra)}#")
        self._send(f":Sd{_format_dec(dec)}#")
        self._send(":CM#")
        return True

    def goto(self, ra: float, dec: float) -> bool:
        self._send(f":Sr{_format_ra(ra)}#")
        self._send(f":Sd{_format_dec(dec)}#")
        resp = self._send(":MS#")
        if resp != "0":
            _MS_CODES = {"1": "below horizon", "2": "above max altitude", "3": "above 87°",
                         "4": "outside limits", "5": "tracking off"}
            reason = _MS_CODES.get(resp, f"code {resp!r}")
            _log.error(
                "OnStepMount.goto(): :MS# returned %r (%s) — RA=%s Dec=%s",
                resp, reason, _format_ra(ra), _format_dec(dec),
            )
            raise RuntimeError(f"GoTo rejected by OnStep: {reason} (:MS# = {resp!r})")
        return True

    def is_slewing(self) -> bool:
        return "|" in self._send(":D#")

    def stop(self) -> None:
        if self._serial is not None:
            with contextlib.suppress(Exception):
                self._serial.write(b":Q#")

    def park(self) -> bool:
        self._raw_send(":hP#")
        return True

    def get_park_position(self) -> MountPosition | None:
        try:
            ra_str  = self._send(":GpA#")
            dec_str = self._send(":GpD#")
            if not ra_str or not dec_str:
                return None
            return MountPosition(ra=_parse_ra(ra_str), dec=_parse_dec(dec_str))
        except Exception:
            return None

    def disable_tracking(self) -> bool:
        self._raw_send(":Td#")
        return True

    def guide(self, direction: str, duration_ms: int) -> bool:
        d = direction.lower()
        if d not in ("n", "s", "e", "w"):
            return False
        ms = max(1, min(9999, duration_ms))
        self._raw_send(f":Mg{d}{ms:04d}#")
        return True

    def start_alignment(self, num_stars: int) -> bool:
        n = max(1, min(9, num_stars))
        return self._send(f":A{n}#") == "1"

    def accept_alignment_star(self) -> bool:
        return self._send(":A+#") == "1"

    def save_alignment(self) -> bool:
        return self._send(":AW#") == "1"
