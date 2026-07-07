"""LocationSource — where the currently active observer location came from.

Five sources:
  CONFIG_FILE    — loaded from [observer] in config.toml at startup (the Home baseline).
  GPS_FIX        — populated from a local GPSD fix (services/gpsd_service.py).
  IP_LOOKUP      — populated from a user-triggered IP-geolocation lookup.
  USER_ENTERED   — the user typed/edited lat/lon/height_m by hand.
  SAVED_LOCATION — recalled from the [locations.<name>] library by name.
"""
from __future__ import annotations

import enum


class LocationSource(enum.Enum):
    CONFIG_FILE    = "CONFIG_FILE"
    GPS_FIX        = "GPS_FIX"
    IP_LOOKUP      = "IP_LOOKUP"
    USER_ENTERED   = "USER_ENTERED"
    SAVED_LOCATION = "SAVED_LOCATION"


def is_valid(value: str) -> bool:
    """Return True if *value* is a recognised LocationSource member name."""
    return value in LocationSource.__members__
