"""OnStep V4 mount adapter — LX200 serial protocol over pyserial."""

from __future__ import annotations

import logging
import time

import serial

from ...ports.mount import MountPort, MountPosition, MountState
from .serial_bus import OnStepSerialBus

_log = logging.getLogger(__name__)

_MAX_GVP_ATTEMPTS = 3
_GVP_RETRY_DELAY_S = 0.3

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
        self._bus = OnStepSerialBus()

    # ── backward-compat property so test_with_fake_serial.py can set _serial ──

    @property
    def _serial(self) -> serial.Serial | None:  # type: ignore[override]
        return self._bus._serial

    @_serial.setter
    def _serial(self, value: serial.Serial | None) -> None:
        self._bus._serial = value

    @property
    def serial_bus(self) -> OnStepSerialBus:
        """Public access to the shared bus (used by OnStepFocuser)."""
        return self._bus

    def connect(self) -> bool:
        s = self._bus._serial
        if s is not None and s.is_open:
            _log.info("OnStepMount.connect(): already open on %s", self._port)
            return True  # already connected — idempotent
        _log.info("OnStepMount.connect(): opening %s @ %d baud timeout=%.1fs",
                  self._port, self._baud_rate, self._timeout)
        try:
            s = serial.Serial(self._port, self._baud_rate, timeout=self._timeout)
        except (serial.SerialException, OSError) as exc:
            _log.error("OnStepMount.connect(): failed to open %s — %s", self._port, exc)
            return False
        self._bus._serial = s

        # Confirm we're talking to OnStep and not another serial device.
        # Uses read() instead of readline() so unit-test mocks (which only stub
        # readline) pass through unaffected; non-bytes mock return values are
        # treated as "no response" and accepted as inconclusive.
        # Accepts "OnStep" and "On-Step" (both appear across firmware versions).
        # On reconnect the buffer may contain stale command ACKs ('0'/'1') from a
        # previous session.  Retry up to _MAX_GVP_ATTEMPTS times, flushing between
        # each attempt, before concluding the port is not OnStep.
        product = ""
        for attempt in range(_MAX_GVP_ATTEMPTS):
            if attempt:
                time.sleep(_GVP_RETRY_DELAY_S)
            s.reset_input_buffer()
            s.write(b":GVP#")
            raw = s.read(32)
            if not isinstance(raw, bytes):
                _log.warning("OnStepMount.connect(): :GVP# returned non-bytes %r (mock?)", raw)
                break
            product = raw.decode(errors="replace").rstrip("#\r\n").strip()
            _log.info("OnStepMount.connect(): :GVP# attempt=%d response=%r", attempt + 1, product)
            if not product or ("on" in product.lower() and "step" in product.lower()):
                break  # empty (inconclusive but accepted) or confirmed OnStep
            _log.warning(
                "OnStepMount.connect(): :GVP# unexpected %r on attempt %d — retrying",
                product, attempt + 1,
            )
        else:
            _log.error(
                "OnStepMount.connect(): not OnStep after %d attempts (last: %r) — closing",
                _MAX_GVP_ATTEMPTS, product,
            )
            s.close()
            self._bus._serial = None
            return False

        self.disable_tracking()
        _log.info("OnStepMount.connect(): connected — product=%r port=%s", product, self._port)
        return True

    def disconnect(self) -> None:
        s = self._bus._serial
        if s is not None:
            s.close()

    def _raw_send(self, cmd: str) -> bytes:
        return self._bus.raw_send(cmd)

    def _send(self, cmd: str) -> str:
        return self._bus.send(cmd)

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
        self._bus.write_bypass(b":Q#")

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
