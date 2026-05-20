"""Site, hardware, and session configuration.

Settings are loaded from the first config file found in this order:
  1. ~/.SmartTScope/config.toml          (primary — per-installation)
  2. <CWD>/smart_telescope.toml          (dev / CI fallback)
  3. <project root>/smart_telescope.toml (last-resort dev fallback)

Copy templates/config.toml to ~/.SmartTScope/config.toml to get started.
Environment variables override any setting from the file.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path


class ConfigError(Exception):
    """Raised when config.toml contains a TOML syntax error."""


# ── locate and load config file ───────────────────────────────────────────────

_USER_DIR = Path.home() / ".SmartTScope"
_SEARCH_PATHS = [
    _USER_DIR / "config.toml",
    Path.cwd() / "smart_telescope.toml",
    Path(__file__).parent.parent / "smart_telescope.toml",
]


def _load_config_from_disk() -> tuple[dict, ConfigError | None]:
    """Load the first found config file. Returns (cfg_dict, error_or_None)."""
    for path in _SEARCH_PATHS:
        if path.exists():
            try:
                with path.open("rb") as fh:
                    return tomllib.load(fh), None
            except tomllib.TOMLDecodeError as e:
                return {}, ConfigError(f"Config parse error in {path}: {e}")
    return {}, None


_cfg, _load_error = _load_config_from_disk()


def check_load_error() -> None:
    """Raise ConfigError if the config file failed to parse.

    Call this at startup (RuntimeContext.connect_devices) so parse errors
    surface as a structured exception rather than a silent sys.exit.
    """
    if _load_error:
        raise _load_error


def _get(section: str, key: str, default: str) -> str:
    """Return TOML value, falling back to *default*. Used before env-var override."""
    val = _cfg.get(section, {}).get(key)
    return str(val) if val is not None else default


# ── observer ──────────────────────────────────────────────────────────────────

OBSERVER_LAT: float = float(os.environ.get("OBSERVER_LAT", _get("observer", "lat", "50.336")))
OBSERVER_LON: float = float(os.environ.get("OBSERVER_LON", _get("observer", "lon", "8.533")))

# ── hardware (TOML only — deps.py applies env-var override at runtime) ────────

ONSTEP_PORT: str      = _get("hardware", "onstep_port",     "")
GPS_PORT: str         = _get("hardware", "gps_port",        "")
DEW_CONTROL_PORT: str = _get("hardware", "dew_control_port", "")

# ── cameras ───────────────────────────────────────────────────────────────────
# Reads [cameras] section (role → SDK index).  Falls back to legacy
# hardware.touptek_index mapped to the "main" role so existing installs keep
# working without a config change.

def _parse_cameras() -> dict[str, str | int]:
    """Parse [cameras] section; values may be int (SDK index) or str (model name)."""
    section = _cfg.get("cameras", {})
    if section:
        result: dict[str, str | int] = {}
        for role, val in section.items():
            result[role] = int(val) if isinstance(val, (int, float)) else str(val)
        return result
    legacy = _get("hardware", "touptek_index", "")
    if legacy:
        return {"main": int(legacy)}
    return {}

CAMERAS: dict[str, str | int] = _parse_cameras()
# Backward-compat: TOUPTEK_INDEX may now be a model-name string (e.g. "G3M678M") or "0".
TOUPTEK_INDEX: str = str(CAMERAS["main"]) if "main" in CAMERAS else ""


def _parse_camera_serials() -> dict[str, str]:
    """Parse [camera_serials] section: model_name -> serial_number."""
    return {str(k): str(v) for k, v in _cfg.get("camera_serials", {}).items()}

CAMERA_SERIALS: dict[str, str] = _parse_camera_serials()

# ── ASTAP (TOML only — deps.py applies env-var override at runtime) ───────────

ASTAP_PATH: str        = _get("astap", "path",        "")
ASTAP_CATALOG_DIR: str = _get("astap", "catalog_dir", "")

# ── mount limits ─────────────────────────────────────────────────────────────

MOUNT_MIN_ALT_DEG: float     = float(os.environ.get("MOUNT_MIN_ALT_DEG",     _get("mount_limits", "min_alt_deg",     "10.0")))
MOUNT_MAX_ALT_DEG: float     = float(os.environ.get("MOUNT_MAX_ALT_DEG",     _get("mount_limits", "max_alt_deg",     "88.0")))
MOUNT_HA_EAST_LIMIT_H: float = float(os.environ.get("MOUNT_HA_EAST_LIMIT_H", _get("mount_limits", "ha_east_limit_h", "-5.5")))
MOUNT_HA_WEST_LIMIT_H: float = float(os.environ.get("MOUNT_HA_WEST_LIMIT_H", _get("mount_limits", "ha_west_limit_h", "0.333")))

# ── session ───────────────────────────────────────────────────────────────────

def _expand(p: str) -> str:
    """Expand ~ / ~user in a path string; no-op for empty strings."""
    return str(Path(p).expanduser()) if p else p

STORAGE_DIR: str           = _expand(os.environ.get("STORAGE_DIR",  _get("session", "storage_dir",   "")))
IMAGE_ROOT: str            = _expand(os.environ.get("IMAGE_ROOT",    _get("session", "image_root",    "")))
APP_STATE_DIR: str         = _expand(os.environ.get("APP_STATE_DIR", _get("session", "app_state_dir", "")))
_stars_cfg_raw: str        = _expand(os.environ.get("STARS_CFG",     _get("session", "stars_cfg",     "")))
STARS_CFG: str             = _stars_cfg_raw or str(_USER_DIR / "stars.cfg")
_horizon_raw: str          = _expand(os.environ.get("HORIZON_DAT",   _get("session", "horizon_dat",   "")))
HORIZON_DAT: str           = _horizon_raw  or str(_USER_DIR / "horizon.dat")
PIXEL_SCALE_ARCSEC: float  = float(os.environ.get("PIXEL_SCALE_ARCSEC", _get("session", "pixel_scale_arcsec", "0.38")))

# STORAGE_DIR keeps env-var override because health.py checks it at module level.

# ── telescopes ────────────────────────────────────────────────────────────────

@dataclass
class TelescopeSpec:
    """Physical telescope optics."""
    aperture_mm: float
    focal_mm: float
    type: str = "sct"         # sct | refractor | newt | rc
    obstruction: float = 0.0  # central obstruction as fraction of aperture (0 for refractors)


@dataclass
class OpticalTrainSpec:
    """One complete imaging path: telescope + optional modifier + camera role."""
    telescope: str              # key into TELESCOPES
    camera: str                 # camera role key from CAMERAS
    reducer_factor: float = 1.0  # 1.0=none, 0.63=Celestron reducer, 2.0=Barlow 2×
    focuser: str = ""            # "onstep" | "" (no focuser on this train)
    pixel_scale_arcsec: float = 0.0  # override; 0.0 = derive from focal_mm


def _parse_telescopes() -> dict[str, TelescopeSpec]:
    section = _cfg.get("telescopes", {})
    result: dict[str, TelescopeSpec] = {}
    for name, vals in section.items():
        if isinstance(vals, dict):
            result[name] = TelescopeSpec(
                aperture_mm=float(vals.get("aperture_mm", 0.0)),
                focal_mm=float(vals.get("focal_mm", 0.0)),
                type=str(vals.get("type", "sct")),
                obstruction=float(vals.get("obstruction", 0.0)),
            )
    return result


def _parse_optical_trains() -> dict[str, OpticalTrainSpec]:
    section = _cfg.get("optical_trains", {})
    result: dict[str, OpticalTrainSpec] = {}
    for name, vals in section.items():
        if isinstance(vals, dict):
            result[name] = OpticalTrainSpec(
                telescope=str(vals.get("telescope", "")),
                camera=str(vals.get("camera", "")),
                reducer_factor=float(vals.get("reducer_factor", 1.0)),
                focuser=str(vals.get("focuser", "")),
                pixel_scale_arcsec=float(vals.get("pixel_scale_arcsec", 0.0)),
            )
    return result


TELESCOPES:    dict[str, TelescopeSpec]    = _parse_telescopes()
OPTICAL_TRAINS: dict[str, OpticalTrainSpec] = _parse_optical_trains()

# ── collimation ───────────────────────────────────────────────────────────────

def get_collimation_config() -> "CollimationConfig":
    """Load and validate the [collimation] config section.

    Returns a CollimationConfig with all defaults when the section is absent.
    Raises ValueError (via CollimationConfig.validate) on invalid values.
    """
    from .domain.collimation.config import CollimationConfig
    cfg = CollimationConfig.from_dict(_cfg.get("collimation", {}))
    cfg.validate()
    return cfg
