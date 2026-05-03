"""Site, hardware, and session configuration.

Settings are loaded from ``smart_telescope.toml`` found in the first of:
  1. The current working directory (CWD)
  2. The project root (directory containing this package)

Environment variables override the TOML file and are the same names as before,
so existing deployments keep working without a config file.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

# ── locate and load config file ───────────────────────────────────────────────

_CFG_NAME = "smart_telescope.toml"
_SEARCH_PATHS = [
    Path.cwd() / _CFG_NAME,
    Path(__file__).parent.parent / _CFG_NAME,
]

_cfg: dict = {}
for _p in _SEARCH_PATHS:
    if _p.exists():
        with _p.open("rb") as _fh:
            _cfg = tomllib.load(_fh)
        break


def _get(section: str, key: str, default: str) -> str:
    """Return TOML value, falling back to *default*. Used before env-var override."""
    val = _cfg.get(section, {}).get(key)
    return str(val) if val is not None else default


# ── observer ──────────────────────────────────────────────────────────────────

OBSERVER_LAT: float = float(os.environ.get("OBSERVER_LAT", _get("observer", "lat", "50.336")))
OBSERVER_LON: float = float(os.environ.get("OBSERVER_LON", _get("observer", "lon", "8.533")))

# ── hardware (TOML only — deps.py applies env-var override at runtime) ────────

ONSTEP_PORT: str      = _get("hardware", "onstep_port",     "")
TOUPTEK_INDEX: str    = _get("hardware", "touptek_index",   "")
GPS_PORT: str         = _get("hardware", "gps_port",        "")
DEW_CONTROL_PORT: str = _get("hardware", "dew_control_port", "")

# ── ASTAP (TOML only — deps.py applies env-var override at runtime) ───────────

ASTAP_PATH: str        = _get("astap", "path",        "")
ASTAP_CATALOG_DIR: str = _get("astap", "catalog_dir", "")

# ── mount limits ─────────────────────────────────────────────────────────────

MOUNT_MIN_ALT_DEG: float     = float(os.environ.get("MOUNT_MIN_ALT_DEG",     _get("mount_limits", "min_alt_deg",     "10.0")))
MOUNT_MAX_ALT_DEG: float     = float(os.environ.get("MOUNT_MAX_ALT_DEG",     _get("mount_limits", "max_alt_deg",     "88.0")))
MOUNT_HA_EAST_LIMIT_H: float = float(os.environ.get("MOUNT_HA_EAST_LIMIT_H", _get("mount_limits", "ha_east_limit_h", "-5.5")))
MOUNT_HA_WEST_LIMIT_H: float = float(os.environ.get("MOUNT_HA_WEST_LIMIT_H", _get("mount_limits", "ha_west_limit_h", "0.333")))

# ── session ───────────────────────────────────────────────────────────────────

STORAGE_DIR: str           = os.environ.get("STORAGE_DIR",         _get("session", "storage_dir",        ""))
STARS_CFG: str             = os.environ.get("STARS_CFG",           _get("session", "stars_cfg",          "stars.cfg"))
PIXEL_SCALE_ARCSEC: float  = float(os.environ.get("PIXEL_SCALE_ARCSEC", _get("session", "pixel_scale_arcsec", "0.38")))

# STORAGE_DIR keeps env-var override because health.py checks it at module level.
