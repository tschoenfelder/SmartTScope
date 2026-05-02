from ...ports.focuser import FocuserPort


class MockFocuser(FocuserPort):
    def __init__(self, fail_connect: bool = False, available: bool = True) -> None:
        self._fail_connect = fail_connect
        self._available = available
        self._position: int = 0

    def connect(self) -> bool:
        return not self._fail_connect

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
