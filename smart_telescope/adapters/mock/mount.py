import logging

from ...ports.mount import MountPort, MountPosition, MountState

_log = logging.getLogger(__name__)


class MockMount(MountPort):
    def __init__(
        self,
        fail_connect: bool = False,
        initial_state: MountState = MountState.UNKNOWN,
        fail_unpark: bool = False,
        fail_goto: bool = False,
        at_limit: bool = False,
    ) -> None:
        _log.warning("MockMount initialised — no real mount hardware; all operations are simulated")
        self._fail_connect = fail_connect
        self._state = MountState.AT_LIMIT if at_limit else initial_state
        self._fail_unpark = fail_unpark
        self._fail_goto = fail_goto
        self._position = MountPosition(ra=0.0, dec=0.0)

    def connect(self) -> bool:
        ok = not self._fail_connect
        _log.warning("MockMount.connect(): returning %s (simulated)", ok)
        return ok

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
        # Real OnStep :MS# engages sidereal tracking as part of completing a
        # slew (LX200-protocol behavior) — mirror that here.
        self._state = MountState.TRACKING
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

    def guide(self, direction: str, duration_ms: int) -> bool:
        return direction.lower() in ("n", "s", "e", "w")

    def move(self, direction: str, move_ms: int, rate_preset: int | None = None) -> bool:
        return direction.lower() in ("n", "s", "e", "w")

    def start_alignment(self, num_stars: int) -> bool:
        return True

    def accept_alignment_star(self) -> bool:
        return True

    def save_alignment(self) -> bool:
        return True

    def go_home(self) -> None:
        self._state = MountState.AT_HOME

    def disconnect(self) -> None:
        self._state = MountState.PARKED
