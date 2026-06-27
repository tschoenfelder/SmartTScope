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
            if isinstance(val, dict):
                if val.get("enabled") is False:
                    continue
                if val.get("index") is not None:
                    result[role] = int(val["index"])
                # dict entries without index are handled via CAMERA_SPECS
                continue
            result[role] = int(val) if isinstance(val, (int, float)) else str(val)
        return result
    legacy = _get("hardware", "touptek_index", "")
    if legacy:
        return {"main": int(legacy)}
    return {}

CAMERAS: dict[str, str | int] = _parse_cameras()
# Backward-compat: TOUPTEK_INDEX may now be a model-name string (e.g. "G3M678M") or "0".
TOUPTEK_INDEX: str = str(CAMERAS["main"]) if "main" in CAMERAS else ""


@dataclass(frozen=True)
class CameraSpec:
    role: str
    enabled: bool = True
    backend: str = "native"
    model: str = ""
    name: str = ""
    camera_id: str = ""
    index: int | None = None
    capture_mode: str = "auto"
    setup_profile: str = "default"
    startup_delay_s: float = 0.0
    startup_monitor_interval_s: float = 1.0
    prime_attempts: int = 0
    prime_timeout_s: float = 1.5
    prime_exposure_s: float | None = None
    gain: int = 101
    offset_lcg: int = 0
    offset_hcg: int = 0
    bit_depth: int = 16

    def offset_for(self, conversion_gain: str) -> int:
        return self.offset_hcg if conversion_gain.upper() == "HCG" else self.offset_lcg


def _camera_spec_from_dict(role: str, vals: dict) -> CameraSpec:
    prime_exp_raw = vals.get("prime_exposure_s")
    return CameraSpec(
        role=role,
        enabled=bool(vals.get("enabled", True)),
        backend=str(vals.get("backend", "native")),
        model=str(vals.get("model", "")),
        name=str(vals.get("name", "")),
        camera_id=str(vals.get("camera_id", "")),
        index=int(vals["index"]) if vals.get("index") is not None else None,
        capture_mode=str(vals.get("capture_mode", "auto")),
        setup_profile=str(vals.get("setup_profile", "default")),
        startup_delay_s=float(vals.get("startup_delay_s", 0.0)),
        startup_monitor_interval_s=float(vals.get("startup_monitor_interval_s", 1.0)),
        prime_attempts=int(vals.get("prime_attempts", 0)),
        prime_timeout_s=float(vals.get("prime_timeout_s", 1.5)),
        prime_exposure_s=float(prime_exp_raw) if prime_exp_raw is not None else None,
        gain=int(vals.get("gain", 101)),
        offset_lcg=int(vals.get("offset_lcg", vals.get("offset", 0))),
        offset_hcg=int(vals.get("offset_hcg", vals.get("offset", 0))),
        bit_depth=int(vals.get("bit_depth", 16)),
    )


def _parse_camera_specs() -> dict[str, CameraSpec]:
    section = _cfg.get("cameras", {})
    result: dict[str, CameraSpec] = {}
    if section:
        for role, value in section.items():
            if isinstance(value, dict):
                result[role] = _camera_spec_from_dict(role, value)
            else:
                result[role] = CameraSpec(role=role, index=int(value))
    legacy = _get("hardware", "touptek_index", "")
    if legacy and "main" not in result:
        result["main"] = CameraSpec(role="main", index=int(legacy))
    return result


CAMERA_SPECS: dict[str, CameraSpec] = _parse_camera_specs()


@dataclass(frozen=True)
class CoolingSpec:
    default_target_c: float = -10.0


@dataclass(frozen=True)
class FilterWheelSpec:
    enabled: bool = False
    backend: str = "native"
    model: str = ""
    name: str = ""
    wheel_id: str = ""
    settle_s: float = 1.5
    active_camera_role: str = "main"


@dataclass(frozen=True)
class GuidingSpec:
    primary_role: str = "guide"
    allow_fallback: bool = True
    fallback_after_bad_frames: int = 3
    max_frame_age_s: float = 2.0
    centroid_roi_px: int = 32
    min_peak_snr: float = 5.0
    saturation_fraction: float = 0.98
    measure_only: bool = True


def _parse_cooling_spec() -> CoolingSpec:
    section = _cfg.get("cooling", {})
    return CoolingSpec(default_target_c=float(section.get("default_target_c", -10.0)))


def _parse_filter_wheel_spec() -> FilterWheelSpec:
    section = _cfg.get("filter_wheel", {})
    return FilterWheelSpec(
        enabled=bool(section.get("enabled", False)),
        backend=str(section.get("backend", "native")),
        model=str(section.get("model", "")),
        name=str(section.get("name", "")),
        wheel_id=str(section.get("wheel_id", "")),
        settle_s=float(section.get("settle_s", 1.5)),
        active_camera_role=str(section.get("active_camera_role", "main")),
    )


def _parse_guiding_spec() -> GuidingSpec:
    section = _cfg.get("guiding", {})
    return GuidingSpec(
        primary_role=str(section.get("primary_role", "guide")),
        allow_fallback=bool(section.get("allow_fallback", True)),
        fallback_after_bad_frames=int(section.get("fallback_after_bad_frames", 3)),
        max_frame_age_s=float(section.get("max_frame_age_s", 2.0)),
        centroid_roi_px=int(section.get("centroid_roi_px", 32)),
        min_peak_snr=float(section.get("min_peak_snr", 5.0)),
        saturation_fraction=float(section.get("saturation_fraction", 0.98)),
        measure_only=bool(section.get("measure_only", True)),
    )


COOLING: CoolingSpec = _parse_cooling_spec()
FILTER_WHEEL: FilterWheelSpec = _parse_filter_wheel_spec()
GUIDING: GuidingSpec = _parse_guiding_spec()


def _parse_camera_serials() -> dict[str, str]:
    """Parse [camera_serials] section: model_name -> serial_number."""
    return {str(k): str(v) for k, v in _cfg.get("camera_serials", {}).items()}

CAMERA_SERIALS: dict[str, str] = _parse_camera_serials()

# ── camera offsets ────────────────────────────────────────────────────────────


def _parse_camera_offsets() -> dict[str, dict[str, int]]:
    """Parse [camera_offsets.{model}] sections: model -> {lcg/hcg/hdr -> int}."""
    section = _cfg.get("camera_offsets", {})
    result: dict[str, dict[str, int]] = {}
    for model_name, gain_offsets in section.items():
        if isinstance(gain_offsets, dict):
            result[str(model_name)] = {k.lower(): int(v) for k, v in gain_offsets.items()}
    return result


CAMERA_OFFSETS: dict[str, dict[str, int]] = _parse_camera_offsets()

# ── ASTAP (TOML only — deps.py applies env-var override at runtime) ───────────

ASTAP_PATH: str        = _get("astap", "path",        "")
ASTAP_CATALOG_DIR: str = _get("astap", "catalog_dir", "")

# ── focuser backlash (M7-004 / CFG-004) ──────────────────────────────────────

FOCUSER_BACKLASH_STEPS: int = int(os.environ.get(
    "FOCUSER_BACKLASH_STEPS", _get("focuser", "backlash_steps", "80")
))
FOCUSER_BACKLASH_ENABLED: bool = (os.environ.get(
    "FOCUSER_BACKLASH_ENABLED", _get("focuser", "backlash_compensation_enabled", "false")
).lower() not in ("false", "0", "no", ""))

# ── mount limits ─────────────────────────────────────────────────────────────

MOUNT_MIN_ALT_DEG: float     = float(os.environ.get("MOUNT_MIN_ALT_DEG",     _get("mount_limits", "min_alt_deg",     "10.0")))
MOUNT_MAX_ALT_DEG: float     = float(os.environ.get("MOUNT_MAX_ALT_DEG",     _get("mount_limits", "max_alt_deg",     "88.0")))
MOUNT_HA_EAST_LIMIT_H: float = float(os.environ.get("MOUNT_HA_EAST_LIMIT_H", _get("mount_limits", "ha_east_limit_h", "-5.5")))
MOUNT_HA_WEST_LIMIT_H: float = float(os.environ.get("MOUNT_HA_WEST_LIMIT_H", _get("mount_limits", "ha_west_limit_h", "0.333")))

# ── OnStep time/location verification tolerances (M8-008 / REQ-TIME-003) ─────

ONSTEP_TIME_TOLERANCE_S: float     = float(os.environ.get("ONSTEP_TIME_TOLERANCE_S",     _get("mount", "onstep_time_tolerance_s",     "10.0")))
ONSTEP_LOCATION_TOLERANCE_M: float = float(os.environ.get("ONSTEP_LOCATION_TOLERANCE_M", _get("mount", "onstep_location_tolerance_m", "100.0")))

# ── Raspberry Pi time trust session expiry (M8-009 / DEC-004, DEC-005) ───────
# Trust never survives an application restart (in-memory only; persist_trust_across_restart = false).
# USER_CONFIRMED and ONSTEP_COMPARISON trust expire within the session after this many minutes.

SESSION_TRUST_EXPIRY_MINUTES: int = int(os.environ.get("SESSION_TRUST_EXPIRY_MINUTES", _get("time_location", "session_trust_expiry_minutes", "120")))


def build_onstep_safety_config():
    """Build OnStepSafetyConfig from this module's config values.

    Called by OnStepMount._default_safety_config() at adapter construction time.
    """
    from .adapters.onstep import OnStepSafetyConfig

    state_dir = APP_STATE_DIR or str(_USER_DIR)
    return OnStepSafetyConfig(
        observer_lat=OBSERVER_LAT,
        observer_lon=OBSERVER_LON,
        min_alt_deg=MOUNT_MIN_ALT_DEG,
        max_alt_deg=MOUNT_MAX_ALT_DEG,
        ha_east_limit_h=MOUNT_HA_EAST_LIMIT_H,
        ha_west_limit_h=MOUNT_HA_WEST_LIMIT_H,
        horizon_path=HORIZON_DAT if HORIZON_DAT and os.path.exists(HORIZON_DAT) else "",
        state_file=str(Path(state_dir) / "onstep_last_state.json"),
        mechanical_calibration_file=str(Path(state_dir) / "onstep_calibration.json"),
        require_home_confirmation=True,
        time_trust_source="raspberry_plausible",
        allow_broad_onstep_limits=True,
        onstep_time_tolerance_s=ONSTEP_TIME_TOLERANCE_S,
        onstep_location_tolerance_m=ONSTEP_LOCATION_TOLERANCE_M,
    )

# ── session ───────────────────────────────────────────────────────────────────

def _expand(p: str) -> str:
    """Expand ~ / ~user in a path string; no-op for empty strings."""
    return str(Path(p).expanduser()) if p else p

STORAGE_DIR: str           = _expand(os.environ.get("STORAGE_DIR",  _get("session", "storage_dir",   "")))
IMAGE_ROOT: str            = _expand(os.environ.get("IMAGE_ROOT",    _get("session", "image_root",    "")))
APP_STATE_DIR: str         = _expand(os.environ.get("APP_STATE_DIR", _get("session", "app_state_dir", "")))
COMMAND_HISTORY_DIR: str   = _expand(os.environ.get("COMMAND_HISTORY_DIR", _get("session", "command_history_dir", str(_USER_DIR / "commands"))))
LOG_DIR: str               = _expand(os.environ.get("LOG_DIR",               _get("session", "log_dir",               str(_USER_DIR / "logs"))))

# ── Diagnostic frame storage (M8-017 / REQ-FRAME-001) ────────────────────────
DIAGNOSTIC_FRAMES_ENABLED: bool = (
    os.environ.get(
        "DIAGNOSTIC_FRAMES_ENABLED",
        _get("diagnostic_frames", "enabled", "true"),
    ).lower() not in ("false", "0", "no", "")
)
DIAGNOSTIC_FRAMES_STORE_MODE: str = os.environ.get(
    "DIAGNOSTIC_FRAMES_STORE_MODE",
    _get("diagnostic_frames", "store_mode", "debug_or_failure"),
)
DIAGNOSTIC_FRAMES_RETENTION_DAYS: int = int(os.environ.get(
    "DIAGNOSTIC_FRAMES_RETENTION_DAYS",
    _get("diagnostic_frames", "retention_days", "2"),
))
DIAGNOSTIC_FRAMES_DIR: str = _expand(os.environ.get(
    "DIAGNOSTIC_FRAMES_DIR",
    _get("diagnostic_frames", "frame_dir", str(_USER_DIR / "diagnostic_frames")),
))

# ── Operation policy (M8-013 / REQ-GOTO-003) ─────────────────────────────────
# When true, direct RA/DEC GoTo is allowed even when Raspberry Pi time is not trusted.
ALLOW_DIRECT_RADEC_GOTO_WITHOUT_RASPBERRY_TIME_TRUST: bool = (
    os.environ.get(
        "ALLOW_DIRECT_RADEC_GOTO_WITHOUT_RASPBERRY_TIME_TRUST",
        _get("operation_policy", "allow_direct_radec_goto_without_raspberry_time_trust", "false"),
    ).lower() not in ("false", "0", "no", "")
)
_stars_cfg_raw: str        = _expand(os.environ.get("STARS_CFG",     _get("session", "stars_cfg",     "")))
STARS_CFG: str             = _stars_cfg_raw or str(_USER_DIR / "stars.cfg")
_horizon_raw: str          = _expand(os.environ.get("HORIZON_DAT",   _get("session", "horizon_dat",   "")))
HORIZON_DAT: str           = _horizon_raw  or str(_USER_DIR / "horizon.dat")
PIXEL_SCALE_ARCSEC: float  = float(os.environ.get("PIXEL_SCALE_ARCSEC", _get("session", "pixel_scale_arcsec", "0.295")))

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
