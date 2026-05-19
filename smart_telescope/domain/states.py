from enum import Enum, auto


class SessionState(Enum):
    IDLE = auto()
    CONNECTED = auto()
    MOUNT_READY = auto()
    ALIGNED = auto()
    SLEWED = auto()
    CENTERED = auto()            # centered within tolerance
    CENTERING_DEGRADED = auto()  # max iterations exceeded; session continues with warning
    FOCUSING = auto()
    PREVIEWING = auto()
    STACKING = auto()
    STACK_COMPLETE = auto()
    SAVED = auto()
    FAILED = auto()
