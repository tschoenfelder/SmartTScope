"""CameraDiagnosticReport — per-camera extended setup check result (M8-019 / REQ-SETUP-001..002)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CameraDiagnosticStatus(str, Enum):
    NOT_ATTEMPTED     = "not_attempted"
    DISCONNECTED      = "disconnected"      # configured but not SDK-detected
    INACTIVE          = "inactive"          # detected but not assigned to any train/setup role
    OPERATION_BLOCKED = "operation_blocked" # gate prevents the check
    CAPTURE_FAILED    = "capture_failed"
    AUTO_GAIN_FAILED  = "auto_gain_failed"
    INSUFFICIENT_STARS = "insufficient_stars"
    METADATA_MISSING  = "metadata_missing"
    ASTAP_FAILED      = "astap_failed"
    SOLVED            = "solved"


@dataclass
class CameraDiagnosticReport:
    """19-field diagnostic record for one camera (REQ-SETUP-001).

    Produced by run_camera_diagnostic() in setup_check_service.py.
    """
    # Identity (4 fields)
    camera_id:         str
    camera_role:       str
    optical_train_id:  str
    camera_index:      int

    # Config / detection state (3 fields)
    is_enabled_in_config:  bool
    is_assigned_to_train:  bool
    is_sdk_detected:       bool

    # Outcome (2 fields)
    status:        CameraDiagnosticStatus
    status_detail: str = ""

    # Capture parameters (3 fields)
    exposure_ms_used: float | None = None
    gain_used:        int | None   = None
    offset_used:      int | None   = None

    # Frame metadata (2 fields)
    frame_captured_at: str | None = None  # ISO-8601 UTC
    frame_path:        str | None = None  # path if saved as FITS

    # Image analysis (3 fields)
    star_count:      int | None   = None
    median_fwhm_px:  float | None = None
    background_adu:  float | None = None

    # Plate-solve result (2 fields)
    ra_hours:  float | None = None
    dec_deg:   float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "camera_id":            self.camera_id,
            "camera_role":          self.camera_role,
            "optical_train_id":     self.optical_train_id,
            "camera_index":         self.camera_index,
            "is_enabled_in_config": self.is_enabled_in_config,
            "is_assigned_to_train": self.is_assigned_to_train,
            "is_sdk_detected":      self.is_sdk_detected,
            "status":               self.status.value,
            "status_detail":        self.status_detail,
            "exposure_ms_used":     self.exposure_ms_used,
            "gain_used":            self.gain_used,
            "offset_used":          self.offset_used,
            "frame_captured_at":    self.frame_captured_at,
            "frame_path":           self.frame_path,
            "star_count":           self.star_count,
            "median_fwhm_px":       self.median_fwhm_px,
            "background_adu":       self.background_adu,
            "ra_hours":             self.ra_hours,
            "dec_deg":              self.dec_deg,
        }

    def to_json_line(self) -> str:
        return json.dumps(self.to_dict(), default=str)
