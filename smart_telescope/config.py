"""Site and observer configuration.

All settings default to Usingen, Hesse, Germany (50.336°N, 8.533°E).
Override by setting environment variables before starting the server:

  OBSERVER_LAT  — decimal degrees, north-positive  (default: 50.336)
  OBSERVER_LON  — decimal degrees, east-positive   (default:  8.533)
  STARS_CFG     — path to stars.cfg custom-target file (default: stars.cfg in CWD)

Mount position limits (enforced on every GoTo):
  MOUNT_MIN_ALT_DEG        — minimum altitude above horizon in degrees     (default: 10.0)
  MOUNT_MAX_ALT_DEG        — maximum altitude / zenith exclusion in degrees (default: 88.0)
  MOUNT_HA_EAST_LIMIT_H    — easternmost hour angle allowed (negative, hours) (default: -5.5)
  MOUNT_HA_WEST_LIMIT_H    — degrees past meridian before counterweight exceeds 5° above
                             scope, expressed in hours                       (default: 0.333)
"""

from __future__ import annotations

import os

OBSERVER_LAT: float = float(os.environ.get("OBSERVER_LAT", "50.336"))
OBSERVER_LON: float = float(os.environ.get("OBSERVER_LON", "8.533"))
STARS_CFG: str = os.environ.get("STARS_CFG", "stars.cfg")
PIXEL_SCALE_ARCSEC: float = float(os.environ.get("PIXEL_SCALE_ARCSEC", "0.38"))  # C8 native focal length

# Mount position limits
MOUNT_MIN_ALT_DEG: float     = float(os.environ.get("MOUNT_MIN_ALT_DEG",     "10.0"))
MOUNT_MAX_ALT_DEG: float     = float(os.environ.get("MOUNT_MAX_ALT_DEG",     "88.0"))
MOUNT_HA_EAST_LIMIT_H: float = float(os.environ.get("MOUNT_HA_EAST_LIMIT_H", "-5.5"))
MOUNT_HA_WEST_LIMIT_H: float = float(os.environ.get("MOUNT_HA_WEST_LIMIT_H", "0.333"))
