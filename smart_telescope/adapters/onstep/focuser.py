"""OnStep V4 focuser adapter — LX200 F-commands over pyserial."""

from __future__ import annotations

import serial

from ...ports.focuser import FocuserPort


class OnStepFocuser(FocuserPort):
    """Controls the OnStep focuser via LX200 F-commands on a shared serial port.

    NOTE: OnStep uses a single serial port for both mount and focuser. When
    OnStepMount is active on the same port, do not instantiate both adapters
    simultaneously — they will conflict. For integration, pass the focuser
    a dedicated port object or use a shared-serial wrapper in the future.
    """

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
            reply = self._send(":FA#")
            return reply == "1"
        except (serial.SerialException, OSError):
            return False

    def disconnect(self) -> None:
        if self._serial is not None:
            self._serial.close()
            self._serial = None

    def _send(self, cmd: str) -> str:
        if self._serial is None:
            return ""
        self._serial.write(cmd.encode())
        return bytes(self._serial.readline()).decode(errors="replace").rstrip("#\r\n")

    def _send_no_reply(self, cmd: str) -> None:
        if self._serial is not None:
            self._serial.write(cmd.encode())

    def get_position(self) -> int:
        reply = self._send(":FG#")
        try:
            return int(reply)
        except ValueError:
            return 0

    def move(self, steps: int) -> None:
        self._send(f":FS{steps}#")

    def is_moving(self) -> bool:
        return self._send(":FT#") == "M"

    def stop(self) -> None:
        self._send_no_reply(":FQ#")
