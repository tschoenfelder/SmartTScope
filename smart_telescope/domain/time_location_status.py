from enum import Enum, auto


class TimeLocationStatus(Enum):
    UNKNOWN    = auto()  # not yet checked (startup, connect failed, or check error)
    VERIFIED   = auto()  # within tolerance or user approved push to OnStep
    UNVERIFIED = auto()  # user skipped push; GoTo/tracking/sync are blocked
