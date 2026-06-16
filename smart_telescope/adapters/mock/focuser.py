import logging

from ...ports.focuser import FocuserMoveResult, FocuserPort, FocuserStatus

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

    def status(self) -> FocuserStatus:
        avail = self._available
        return FocuserStatus(
            available=avail,
            position=self._position if avail else 0,
            max_position=self.get_max_position(),
            moving=False,
        )

    def move_absolute(self, steps: int) -> FocuserMoveResult:
        start = self._position
        self._position = steps
        return FocuserMoveResult(
            accepted=True,
            target_position=steps,
            start_position=start,
            onstep_reply="1",
        )

    def move(self, steps: int) -> None:
        self._position += steps

    def get_position(self) -> int:
        return self._position

    def get_max_position(self) -> int:
        return 5000

    def is_moving(self) -> bool:
        return False

    def stop(self) -> None:
        pass
