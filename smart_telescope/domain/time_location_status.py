from enum import Enum, auto


class TimeLocationStatus(Enum):
    UNKNOWN    = auto()  # not yet checked (startup, connect failed, or check error)
    VERIFIED   = auto()  # within tolerance or user approved push to OnStep
    UNVERIFIED = auto()  # user skipped push; GoTo/tracking/sync are blocked


# OnStep's firmware clock defaults to 1988-01-01 after a factory reset / dead
# backup battery. Any OnStep clock year before this cutoff is treated as
# "obviously invalid" rather than a genuine (if large) time mismatch, and may
# be auto-corrected at connect time when the Pi's own clock is trusted via
# GPS/NTP — see session_connect() in api/session.py.
OBVIOUSLY_INVALID_CLOCK_YEAR_CUTOFF = 2020
