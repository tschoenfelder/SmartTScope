"""ExposureCapabilityResult — 5-step exposure sweep with 13-field per-step diagnostics (M8-023).

The capability test captures frames at increasing exposures and stops early when
tracking blur or saturation is detected.  Results are advisory — suggested values
are never written to config without user confirmation (OPEN-004: REQ-AG-003..004).
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

TEST_EXPOSURES_S: tuple[float, ...] = (0.5, 1.0, 2.0, 4.0, 8.0)

_SATURATION_THRESHOLD_PCT = 1.0   # saturated_pixel_ratio above which we stop
_BLUR_ELONGATION_THRESHOLD = 2.0  # elongation ratio above which blur is suspected
_BLUR_GROWTH_FACTOR = 1.5         # ratio must grow by this factor to trigger stop


@dataclass
class ExposureStepDiagnostics:
    """Per-step diagnostics for one exposure in the capability test (13 fields)."""

    exposure_s: float
    number_of_stars_detected: int | None
    background_median_adu: float
    background_stddev_adu: float
    saturated_pixel_ratio: float     # % of pixels at/above 99.5% of ADC range
    black_clipped_pixel_ratio: float # % of pixels at 0
    median_fwhm_px: float | None     # None when < 5 stars detected
    median_hfr_px: float | None      # None when < 5 stars detected (≈ fwhm/2)
    exposure_limit_reached: bool     # True if this is the last allowed exposure
    gain_limit_reached: bool
    offset_limit_reached: bool
    tracking_blur_suspected: bool    # elongation ratio > threshold and grew vs prev
    reason_for_next_step: str | None # why we advanced to the next step
    reason_for_stop: str | None      # set only on the last step of the test

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ExposureCapabilityResult:
    """Aggregated result of the 5-step exposure capability test."""

    steps: list[ExposureStepDiagnostics] = field(default_factory=list)
    recommended_exposure_s: float | None = None  # last good step before any stop condition
    stopped_early: bool = False
    stop_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "steps":                 [s.to_dict() for s in self.steps],
            "recommended_exposure_s": self.recommended_exposure_s,
            "stopped_early":         self.stopped_early,
            "stop_reason":           self.stop_reason,
        }

    def to_json_line(self) -> str:
        return json.dumps(self.to_dict(), default=str)
