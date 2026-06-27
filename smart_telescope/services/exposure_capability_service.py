"""Exposure capability test — sweep 5 exposures, collect 13-field diagnostics per step.

Never writes config.  Results are advisory (OPEN-004 / REQ-AG-003..004).
"""
from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

import numpy as np

from ..domain.autogain import measure_elongation_ratio
from ..domain.exposure_capability import (
    TEST_EXPOSURES_S,
    _BLUR_ELONGATION_THRESHOLD,
    _BLUR_GROWTH_FACTOR,
    _SATURATION_THRESHOLD_PCT,
    ExposureCapabilityResult,
    ExposureStepDiagnostics,
)
from ..ports.camera import CameraPort, CaptureAbortedError

if TYPE_CHECKING:
    pass

_log = logging.getLogger(__name__)

_STAR_THRESHOLD_FACTOR = 3.0  # multiple of background stddev above which a pixel is a star
_MIN_STAR_AREA = 4             # minimum pixel area to count as a star
_MIN_STARS_FOR_FWHM = 5       # need at least this many stars for reliable FWHM


def _analyse_step(pixels: np.ndarray, bit_depth: int = 16) -> dict:  # type: ignore[type-arg]
    """Compute all numerical diagnostics for one captured frame."""
    adc_max = float((1 << bit_depth) - 1)
    flat = pixels.ravel().astype(np.float64)

    # Background: median and stddev of pixels below 80th percentile
    p80 = float(np.percentile(flat, 80))
    bg_mask = flat <= p80
    bg_pixels = flat[bg_mask]
    background_median_adu = float(np.median(bg_pixels))
    background_stddev_adu = float(np.std(bg_pixels)) if len(bg_pixels) > 1 else 0.0

    # Saturation: pixels at or above 99.5% of ADC max
    sat_threshold = 0.995 * adc_max
    saturated_pixel_ratio = float(np.mean(flat >= sat_threshold) * 100.0)

    # Black-clipped: pixels at exactly 0
    black_clipped_pixel_ratio = float(np.mean(flat == 0.0) * 100.0)

    # Star detection using scipy if available, otherwise numpy fallback
    number_of_stars: int | None = None
    median_fwhm_px: float | None = None
    median_hfr_px: float | None = None

    threshold = background_median_adu + _STAR_THRESHOLD_FACTOR * (background_stddev_adu + 1.0)
    star_mask = pixels > threshold

    try:
        from scipy.ndimage import label as _label, find_objects as _find_objects
        labeled, n_labels = _label(star_mask)
        areas: list[float] = []
        if n_labels > 0:
            objects = _find_objects(labeled)
            for i, slices in enumerate(objects):
                if slices is None:
                    continue
                region = labeled[slices] == (i + 1)
                area = int(region.sum())
                if area >= _MIN_STAR_AREA:
                    areas.append(float(area))
        number_of_stars = len(areas)
        if len(areas) >= _MIN_STARS_FOR_FWHM:
            fwhm_vals = [2.355 * float(np.sqrt(a / np.pi)) for a in areas]
            median_fwhm_px = float(np.median(fwhm_vals))
            median_hfr_px = median_fwhm_px * 0.5  # Gaussian approximation
    except ImportError:
        # Numpy fallback: star count only
        labeled_np = np.zeros_like(star_mask, dtype=int)
        star_count = 0
        for r in range(star_mask.shape[0]):
            for c in range(star_mask.shape[1]):
                if star_mask[r, c] and labeled_np[r, c] == 0:
                    star_count += 1
                    labeled_np[r, c] = star_count
        number_of_stars = star_count

    return dict(
        number_of_stars_detected=number_of_stars,
        background_median_adu=round(background_median_adu, 1),
        background_stddev_adu=round(background_stddev_adu, 1),
        saturated_pixel_ratio=round(saturated_pixel_ratio, 3),
        black_clipped_pixel_ratio=round(black_clipped_pixel_ratio, 3),
        median_fwhm_px=round(median_fwhm_px, 2) if median_fwhm_px is not None else None,
        median_hfr_px=round(median_hfr_px, 2) if median_hfr_px is not None else None,
    )


def run_exposure_test(
    camera: CameraPort,
    gain: int = 100,
    offset: int = 0,
    bit_depth: int = 16,
    exposures_s: tuple[float, ...] = TEST_EXPOSURES_S,
    cancellation_flag: threading.Event | None = None,
    gain_at_limit: bool = False,
    offset_at_limit: bool = False,
) -> ExposureCapabilityResult:
    """Capture frames at each exposure in *exposures_s* and collect diagnostics.

    Stops early when:
    - saturation_pixel_ratio >= _SATURATION_THRESHOLD_PCT (1%)
    - tracking_blur_suspected (elongation ratio > 2.0 AND grew by > 50%)
    - cancellation_flag is set

    Results are advisory — suggested values are never written to config.

    Args:
        camera:            Connected camera to capture from.
        gain:              Gain to use for all captures.
        offset:            Black-level offset to use for all captures.
        bit_depth:         ADC bit depth for normalisation.
        exposures_s:       Exposures to test (default: 0.5, 1, 2, 4, 8 s).
        cancellation_flag: Set this event to abort the test.
        gain_at_limit:     True if gain is already at its maximum.
        offset_at_limit:   True if offset is already at its maximum.

    Returns:
        ExposureCapabilityResult with one ExposureStepDiagnostics per captured step.
    """
    result = ExposureCapabilityResult()
    prev_elongation: float | None = None
    recommended_exp: float | None = None

    try:
        camera.set_gain(gain)
    except Exception:
        pass
    try:
        camera.set_black_level(offset)
    except Exception:
        pass

    for idx, exp_s in enumerate(exposures_s):
        is_last = (idx == len(exposures_s) - 1)

        if cancellation_flag is not None and cancellation_flag.is_set():
            if result.steps:
                result.steps[-1] = _set_stop(result.steps[-1], "Cancelled by caller")
            result.stopped_early = True
            result.stop_reason = "Cancelled"
            return result

        _log.info("ExposureCapabilityTest: step %d/%d at %.1f s", idx + 1, len(exposures_s), exp_s)
        try:
            frame = camera.capture(exp_s)
        except CaptureAbortedError:
            result.stopped_early = True
            result.stop_reason = "Cancelled (capture aborted)"
            return result
        except Exception as exc:
            result.stopped_early = True
            result.stop_reason = f"Capture failed: {exc}"
            return result

        # Refine bit_depth from frame header if available
        try:
            bd = int(frame.header.get("BITDEPTH", bit_depth))
            if bd != bit_depth:
                bit_depth = bd
        except Exception:
            pass

        diag = _analyse_step(frame.pixels, bit_depth)
        elong = measure_elongation_ratio(frame.pixels)
        blur_suspected = False
        if prev_elongation is not None and elong > _BLUR_ELONGATION_THRESHOLD and elong > prev_elongation * _BLUR_GROWTH_FACTOR:
            blur_suspected = True
        prev_elongation = elong

        reason_next: str | None = None
        reason_stop: str | None = None

        saturated = diag["saturated_pixel_ratio"] >= _SATURATION_THRESHOLD_PCT
        stop_now = saturated or blur_suspected or is_last

        if not stop_now:
            reason_next = "no saturation or blur detected"
        elif saturated:
            reason_stop = f"Saturation detected ({diag['saturated_pixel_ratio']:.2f}% saturated pixels)"
        elif blur_suspected:
            reason_stop = f"Tracking blur detected (elongation ratio {elong:.2f})"
        else:
            reason_stop = "All exposures tested"

        step = ExposureStepDiagnostics(
            exposure_s=exp_s,
            number_of_stars_detected=diag["number_of_stars_detected"],
            background_median_adu=diag["background_median_adu"],
            background_stddev_adu=diag["background_stddev_adu"],
            saturated_pixel_ratio=diag["saturated_pixel_ratio"],
            black_clipped_pixel_ratio=diag["black_clipped_pixel_ratio"],
            median_fwhm_px=diag["median_fwhm_px"],
            median_hfr_px=diag["median_hfr_px"],
            exposure_limit_reached=is_last,
            gain_limit_reached=gain_at_limit,
            offset_limit_reached=offset_at_limit,
            tracking_blur_suspected=blur_suspected,
            reason_for_next_step=reason_next,
            reason_for_stop=reason_stop,
        )
        result.steps.append(step)

        if not blur_suspected and not saturated:
            recommended_exp = exp_s

        if stop_now:
            result.stopped_early = saturated or blur_suspected
            result.stop_reason = reason_stop
            break

    result.recommended_exposure_s = recommended_exp
    return result


def _set_stop(step: ExposureStepDiagnostics, reason: str) -> ExposureStepDiagnostics:
    """Return a copy of *step* with reason_for_stop set."""
    from dataclasses import replace
    return replace(step, reason_for_stop=reason)
