"""Guide camera measurement: centroid, source selection, measure-only controller."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from ..domain.guiding import (
    GuideMeasurement,
    GuideSourceHealth,
    GuideSourceState,
    WouldGuidePulse,
)


@dataclass(frozen=True)
class CentroidConfig:
    roi_px: int = 32
    min_peak_snr: float = 5.0
    saturation_fraction: float = 0.98


class GuideCentroidEstimator:
    """Windowed centroid estimator for guide-star frames."""

    def __init__(self, config: CentroidConfig = CentroidConfig()) -> None:
        self._cfg = config

    def measure(
        self,
        pixels: np.ndarray,
        *,
        role: str,
        sequence: int,
        frame_age_s: float = 0.0,
        target: tuple[float, float] | None = None,
    ) -> GuideMeasurement:
        lum = (
            pixels[:, :, 0].astype(np.float32)
            if pixels.ndim == 3
            else pixels.astype(np.float32)
        )
        h, w = lum.shape

        flat_idx = int(np.argmax(lum))
        peak_y, peak_x = divmod(flat_idx, w)
        peak_val = float(lum[peak_y, peak_x])

        # Saturation check
        if np.issubdtype(pixels.dtype, np.integer):
            dtype_max = float(np.iinfo(pixels.dtype).max)
        else:
            dtype_max = float(np.finfo(pixels.dtype).max)
        if peak_val >= dtype_max * self._cfg.saturation_fraction:
            return GuideMeasurement(
                role=role,
                sequence=sequence,
                accepted=False,
                peak=peak_val,
                saturated=True,
                rejected_reason="saturated",
                frame_age_s=frame_age_s,
                measured_at_monotonic=time.monotonic(),
            )

        # ROI extraction
        half = self._cfg.roi_px // 2
        y0 = max(0, peak_y - half)
        y1 = min(h, peak_y + half + 1)
        x0 = max(0, peak_x - half)
        x1 = min(w, peak_x + half + 1)
        roi = lum[y0:y1, x0:x1]

        # Background from ROI border pixels
        border = np.concatenate(
            [roi[0, :], roi[-1, :], roi[1:-1, 0], roi[1:-1, -1]]
        )
        background = float(np.median(border)) if border.size > 0 else 0.0
        noise = float(np.std(border)) if border.size > 0 else 1.0

        signal = np.clip(roi - background, 0.0, None)
        peak_signal = peak_val - background
        snr = peak_signal / max(noise, 1.0)

        if snr < self._cfg.min_peak_snr or signal.sum() <= 0:
            return GuideMeasurement(
                role=role,
                sequence=sequence,
                accepted=False,
                peak=peak_val,
                background=background,
                noise=noise,
                rejected_reason="snr_too_low",
                frame_age_s=frame_age_s,
                measured_at_monotonic=time.monotonic(),
            )

        # Weighted centroid in ROI coordinates → full-frame coordinates
        total = float(signal.sum())
        yy, xx = np.indices(signal.shape, dtype=np.float32)
        cx_roi = float((signal * xx).sum()) / total
        cy_roi = float((signal * yy).sum()) / total
        centroid_x = x0 + cx_roi
        centroid_y = y0 + cy_roi

        # FWHM estimate
        half_max = peak_signal * 0.5
        fwhm_mask = signal > half_max
        fwhm_px = float(np.sqrt(fwhm_mask.sum() / np.pi) * 2) if fwhm_mask.any() else None

        error_x = centroid_x - target[0] if target is not None else 0.0
        error_y = centroid_y - target[1] if target is not None else 0.0

        return GuideMeasurement(
            role=role,
            sequence=sequence,
            accepted=True,
            centroid_x=centroid_x,
            centroid_y=centroid_y,
            target_x=target[0] if target is not None else None,
            target_y=target[1] if target is not None else None,
            error_x=error_x,
            error_y=error_y,
            confidence=min(1.0, snr / max(self._cfg.min_peak_snr * 5, 1.0)),
            peak=peak_val,
            background=background,
            noise=noise,
            fwhm_px=fwhm_px,
            frame_age_s=frame_age_s,
            measured_at_monotonic=time.monotonic(),
        )


# ---------------------------------------------------------------------------
# Task 3 stubs — not yet implemented
# ---------------------------------------------------------------------------

class GuideSourceSelector:
    """Not yet implemented — added in Task 3."""

    def __init__(self, *args, **kwargs) -> None:
        raise NotImplementedError("GuideSourceSelector is not yet implemented (Task 3)")


class MeasureOnlyGuideController:
    """Not yet implemented — added in Task 3."""

    def __init__(self, *args, **kwargs) -> None:
        raise NotImplementedError("MeasureOnlyGuideController is not yet implemented (Task 3)")

    def would_pulse(self, *args, **kwargs):
        raise NotImplementedError("MeasureOnlyGuideController is not yet implemented (Task 3)")


def source_state_from_measurement(*args, **kwargs) -> GuideSourceState:
    """Not yet implemented — added in Task 3."""
    raise NotImplementedError("source_state_from_measurement is not yet implemented (Task 3)")
