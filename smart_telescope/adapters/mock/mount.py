from ...ports.mount import MountPort, MountPosition, MountState


class MockMount(MountPort):
    def __init__(
        self,
        fail_connect: bool = False,
        initial_state: MountState = MountState.PARKED,
        fail_unpark: bool = False,
        fail_goto: bool = False,
        at_limit: bool = False,
    ) -> None:
        self._fail_connect = fail_connect
        self._state = MountState.AT_LIMIT if at_limit else initial_state
        self._fail_unpark = fail_unpark
        self._fail_goto = fail_goto
        self._position = MountPosition(ra=0.0, dec=0.0)

    def connect(self) -> bool:
        return not self._fail_connect

    def get_state(self) -> MountState:
        return self._state

    def unpark(self) -> bool:
        if self._fail_unpark:
            return False
        self._state = MountState.UNPARKED
        return True

    def enable_tracking(self) -> bool:
        self._state = MountState.TRACKING
        return True

    def get_position(self) -> MountPosition:
        return self._position

    def sync(self, ra: float, dec: float) -> bool:
        self._position = MountPosition(ra=ra, dec=dec)
        return True

    def goto(self, ra: float, dec: float) -> bool:
        if self._fail_goto:
            return False
        self._position = MountPosition(ra=ra, dec=dec)
        return True

    def is_slewing(self) -> bool:
        return False  # mocks resolve instantly

    def stop(self) -> None:
        self._state = MountState.UNPARKED

    def park(self) -> bool:
        self._state = MountState.PARKED
        return True

    def disable_tracking(self) -> bool:
        self._state = MountState.UNPARKED
        return True

    def disconnect(self) -> None:
        self._state = MountState.PARKED
