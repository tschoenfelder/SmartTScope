"""DiagnosticFrame domain objects (M8-017 / REQ-FRAME-001, M8-018 / REQ-FRAME-002..003)."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class DiagnosticStoreMode(str, Enum):
    ALWAYS          = "always"
    DEBUG_ONLY      = "debug_only"
    FAILURE_ONLY    = "failure_only"
    DEBUG_OR_FAILURE = "debug_or_failure"
    OFF             = "off"


@dataclass
class DiagnosticFrameConfig:
    """Configuration for diagnostic FITS frame storage (REQ-FRAME-001)."""

    enabled:        bool = True
    store_mode:     DiagnosticStoreMode = DiagnosticStoreMode.DEBUG_OR_FAILURE
    retention_days: int  = 2
    frame_dir:      str  = ""      # populated from config; empty = ~/.SmartTScope/diagnostic_frames/


# The 16 required FITS headers (REQ-FRAME-003).
REQUIRED_FITS_HEADERS: tuple[str, ...] = (
    "SESSION",    # session ID (first 8 chars)
    "SECTION",    # log section name
    "RUNID",      # service-call run ID
    "ITER",       # 0-based iteration index
    "CAMERA",     # camera_id string
    "OPTTRAIN",   # optical_train_id string
    "EXPTIME",    # exposure time in seconds
    "GAIN",       # integer gain
    "OFFSET",     # integer offset
    "BINX",       # x binning factor
    "BINY",       # y binning factor
    "PIXSIZE",    # pixel size in µm (float | None)
    "FOCALLEN",   # focal length in mm (float | None)
    "RA",         # right ascension in degrees (float | None)
    "DEC",        # declination in degrees (float | None)
    "TRACKING",   # tracking active (bool, stored as T/F)
    "DATE-OBS",   # ISO 8601 UTC timestamp
)
