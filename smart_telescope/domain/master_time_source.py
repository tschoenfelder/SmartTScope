"""MasterTimeSource — priority-ordered master time/location sources."""
from __future__ import annotations

import enum


class MasterTimeSource(enum.Enum):
    GPS_FIX        = "GPS_FIX"        # gpsd reports a fresh fix (mode >= 2)
    NTP            = "NTP"            # OS NTP synchronized
    USER_CONFIRMED = "USER_CONFIRMED" # user explicitly confirmed Pi clock
    FALLBACK       = "FALLBACK"       # none of the above — time untrusted
