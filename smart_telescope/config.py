"""Site and observer configuration.

All settings default to Usingen, Hesse, Germany (50.336°N, 8.533°E).
Override by setting environment variables before starting the server:

  OBSERVER_LAT  — decimal degrees, north-positive  (default: 50.336)
  OBSERVER_LON  — decimal degrees, east-positive   (default:  8.533)
  STARS_CFG     — path to stars.cfg custom-target file (default: stars.cfg in CWD)
"""

from __future__ import annotations

import os

OBSERVER_LAT: float = float(os.environ.get("OBSERVER_LAT", "50.336"))
OBSERVER_LON: float = float(os.environ.get("OBSERVER_LON", "8.533"))
STARS_CFG: str = os.environ.get("STARS_CFG", "stars.cfg")
PIXEL_SCALE_ARCSEC: float = float(os.environ.get("PIXEL_SCALE_ARCSEC", "0.38"))  # C8 native focal length
