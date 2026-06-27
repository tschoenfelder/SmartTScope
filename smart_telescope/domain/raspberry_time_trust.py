"""RaspberryTimeTrustSource — Raspberry Pi clock trust sources (REQ-TIME-002).

Five sources ordered highest to lowest trust:
  GPSD_FIX          — Pi clock synced directly from a local GPS receiver.
  NTP               — Pi clock synchronised via NTP.
  ONSTEP_COMPARISON — Pi time validated against trusted OnStep clock (DEC-006 chain).
  USER_CONFIRMED    — User explicitly confirmed the Pi clock is correct (with warning).
  NOT_TRUSTED       — No trust basis; mount automation gates remain locked.
"""
from __future__ import annotations

import enum


class RaspberryTimeTrustSource(enum.Enum):
    GPSD_FIX          = "GPSD_FIX"
    NTP               = "NTP"
    USER_CONFIRMED    = "USER_CONFIRMED"
    ONSTEP_COMPARISON = "ONSTEP_COMPARISON"
    NOT_TRUSTED       = "NOT_TRUSTED"


def is_trusted(source: RaspberryTimeTrustSource) -> bool:
    """Return True for any source that unlocks mount automation."""
    return source != RaspberryTimeTrustSource.NOT_TRUSTED
