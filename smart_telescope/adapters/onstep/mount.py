"""OnStep V4 mount adapter — LX200 serial protocol over pyserial."""

from __future__ import annotations

import serial

from ...ports.mount import MountPort, MountPosition, MountState


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

    def connect(self) -> bool:
        try:
            self._serial = serial.Serial(self._port, self._baud_rate, timeout=self._timeout)
            return True
        except (serial.SerialException, OSError):
            return False

    def disconnect(self) -> None:
        if self._serial is not None:
            self._serial.close()

    def _raw_send(self, cmd: str) -> bytes:
        if self._serial is None:
            return b""
        self._serial.write(cmd.encode())
        return self._serial.readline()

    def _send(self, cmd: str) -> str:
        return self._raw_send(cmd).decode(errors="replace").rstrip("#\r\n")

    def get_state(self) -> MountState:
        r = self._send(":GU#")
        if not r:
            return MountState.UNKNOWN
        if "P" in r:
            return MountState.PARKED
        if "S" in r:
            return MountState.SLEWING
        if "E" in r or "W" in r:
            return MountState.AT_LIMIT
        if "T" in r:
            return MountState.TRACKING
        return MountState.UNPARKED

    def unpark(self) -> bool:
        return len(self._raw_send(":hU#")) > 0

    def enable_tracking(self) -> bool:
        return self._send(":Te#") == "1"

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
        return self._send(":MS#") == "0"

    def is_slewing(self) -> bool:
        return "|" in self._send(":D#")

    def stop(self) -> None:
        if self._serial is not None:
            try:
                self._serial.write(b":Q#")
            except Exception:
                pass
