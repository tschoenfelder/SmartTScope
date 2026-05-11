import logging

from ...ports.focuser import FocuserPort

_log = logging.getLogger(__name__)


class MockFocuser(FocuserPort):
    def __init__(self, fail_connect: bool = False, available: bool = False) -> None:
        _log.warning("MockFocuser initialised — no real focuser hardware; all operations are simulated")
        self._fail_connect = fail_connect
        self._available = available
        self._position: int = 0

    def connect(self) -> bool:
        ok = not self._fail_connect
        _log.warning("MockFocuser.connect(): returning %s (simulated)", ok)
        return ok

    def disconnect(self) -> None:
        pass

    @property
    def is_available(self) -> bool:
        return self._available

    def move(self, steps: int) -> None:
        self._position = steps

    def get_position(self) -> int:
        return self._position

    def get_max_position(self) -> int:
        return 5000

    def is_moving(self) -> bool:
        return False

    def stop(self) -> None:
        pass
