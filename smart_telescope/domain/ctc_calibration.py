"""Click-to-center calibration data model — M8-027 / REQ-CLICK-003.

Calibration is keyed by (optical_train_name, binning) and stores the
pixel-to-sky mapping needed to convert a pixel displacement into a mount move.

Stored in ~/.SmartTScope/ctc_calibration.json as a JSON object mapping
"optical_train:binning" → CalibrationRecord.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass

_DEFAULT_MAX_AGE_HOURS = 24


@dataclass
class CTCCalibration:
    """Pixel-to-sky calibration for a specific optical-train/binning pair.

    arcsec_per_px_x: angular scale along the image X axis (arcsec / pixel)
    arcsec_per_px_y: angular scale along the image Y axis (arcsec / pixel)
    rotation_deg: angle between camera X axis and mount RA axis (degrees)
    optical_train: name of the optical train this calibration applies to
    binning: camera binning factor (1, 2, 3, …)
    measured_at: Unix timestamp when calibration was captured
    max_age_hours: calibration expires after this many hours
    """
    arcsec_per_px_x: float
    arcsec_per_px_y: float
    rotation_deg: float
    optical_train: str
    binning: int
    measured_at: float
    max_age_hours: float = _DEFAULT_MAX_AGE_HOURS

    @property
    def key(self) -> str:
        return f"{self.optical_train}:{self.binning}"

    def is_valid(self, now: float | None = None) -> bool:
        t = now if now is not None else time.time()
        age_hours = (t - self.measured_at) / 3600.0
        return age_hours <= self.max_age_hours

    def age_hours(self, now: float | None = None) -> float:
        t = now if now is not None else time.time()
        return (t - self.measured_at) / 3600.0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["is_valid"] = self.is_valid()
        d["age_hours"] = round(self.age_hours(), 2)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "CTCCalibration":
        allowed = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in allowed})
