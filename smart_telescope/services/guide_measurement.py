"""Guide camera measurement: centroid, source selection, measure-only controller."""

from __future__ import annotations

import time
from dataclasses import dataclass

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
            dtype_max = 1.0  # assume normalised float in [0, 1]
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
        if border.size > 0:
            noise = float(1.4826 * np.median(np.abs(border - np.median(border))))
            noise = max(noise, 1.0)  # prevent division by zero on uniform backgrounds
        else:
            noise = 1.0

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



@dataclass(frozen=True)
class GuideControllerConfig:
    deadband_px: float = 0.5
    max_pulse_ms: int = 2000
    min_pulse_ms: int = 50
    aggressiveness: float = 0.7
    ra_only: bool = False
    ms_per_px: float = 100.0


class MeasureOnlyGuideController:
    """Computes would-be guide pulses without sending them to the mount.

    Returns a list of WouldGuidePulse — one per axis with error above deadband.
    """

    def __init__(self, config: GuideControllerConfig = GuideControllerConfig()) -> None:
        self._cfg = config

    def would_pulse(self, measurement: GuideMeasurement) -> list[WouldGuidePulse]:
        if not measurement.accepted:
            return []
        pulses: list[WouldGuidePulse] = []

        def _pulse(axis: str, error: float, pos_dir: str, neg_dir: str) -> None:
            if abs(error) <= self._cfg.deadband_px:
                return
            raw_ms = abs(error) * self._cfg.ms_per_px * self._cfg.aggressiveness
            if raw_ms < self._cfg.min_pulse_ms:
                return  # error too small for mount to correct meaningfully
            clamped = min(int(raw_ms), self._cfg.max_pulse_ms)
            clipped = raw_ms > self._cfg.max_pulse_ms
            direction = pos_dir if error > 0 else neg_dir
            pulses.append(
                WouldGuidePulse(
                    axis=axis,
                    direction=direction,
                    duration_ms=clamped,
                    reason=f"{axis}_error",
                    clipped=clipped,
                )
            )

        if measurement.error_x is not None:
            _pulse("ra", measurement.error_x, "e", "w")
        if not self._cfg.ra_only and measurement.error_y is not None:
            _pulse("dec", measurement.error_y, "s", "n")

        return pulses


class GuideSourceSelector:
    """Selects the active guide source from available GuideSourceState objects.

    Prefers `primary_role` while healthy. Falls back to another healthy role
    when `allow_fallback=True` and primary is `TRANSIENT_BAD`. Never silently
    hides `HARD_FAILED` cameras.
    """

    def __init__(self, primary_role: str = "guide", allow_fallback: bool = True) -> None:
        self._primary = primary_role
        self._allow_fallback = allow_fallback
        self.reason = "primary"

    def select(self, states: dict[str, GuideSourceState]) -> str | None:
        primary = states.get(self._primary)
        if primary and primary.running and primary.health == GuideSourceHealth.HEALTHY:
            self.reason = "primary"
            return self._primary

        if self._allow_fallback and primary and primary.health in (
            GuideSourceHealth.TRANSIENT_BAD,
            GuideSourceHealth.HARD_FAILED,
        ):
            for role, state in states.items():
                if role != self._primary and state.running and state.health == GuideSourceHealth.HEALTHY:
                    self.reason = f"fallback_from_{self._primary}"
                    return role

        if primary and primary.running and primary.health != GuideSourceHealth.HARD_FAILED:
            self.reason = "primary_only_available"
            return self._primary

        self.reason = "no_source"
        return None


def source_state_from_measurement(
    role: str,
    measurement: GuideMeasurement | None,
    *,
    running: bool,
    latest_sequence: int,
    latest_frame_age_s: float | None,
    bad_frame_count: int,
    fallback_after_bad_frames: int,
    hard_failure: str | None = None,
) -> GuideSourceState:
    """Build a GuideSourceState from a measurement result and stream health counters."""
    if hard_failure is not None:
        health = GuideSourceHealth.HARD_FAILED
    elif bad_frame_count >= fallback_after_bad_frames:
        health = GuideSourceHealth.TRANSIENT_BAD
    else:
        health = GuideSourceHealth.HEALTHY
    return GuideSourceState(
        role=role,
        running=running,
        health=health,
        latest_sequence=latest_sequence,
        latest_frame_age_s=latest_frame_age_s,
        bad_frame_count=bad_frame_count,
        hard_failure=hard_failure,
        measurement=measurement,
    )
