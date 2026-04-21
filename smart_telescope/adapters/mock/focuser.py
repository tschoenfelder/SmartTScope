from ...ports.focuser import FocuserPort


class MockFocuser(FocuserPort):
    def __init__(self, fail_connect: bool = False) -> None:
        self._fail_connect = fail_connect
        self._position: int = 0

    def connect(self) -> bool:
        return not self._fail_connect

    def disconnect(self) -> None:
        pass

    def move(self, steps: int) -> None:
        self._position = steps

    def get_position(self) -> int:
        return self._position
