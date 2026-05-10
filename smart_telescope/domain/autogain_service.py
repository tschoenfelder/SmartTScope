"""One-shot Auto Gain service — finds optimal exposure/gain for a camera profile.

Implements the adjustment order from FR-AG-090 (steps 5-13):
  5. Enable driver-assisted auto exposure/gain within strict bounds.
  6. Evaluate full-frame histogram.
  7. If lower end is clipped → raise offset first.
  8. Signal too weak → increase exposure up to profile limit.
  9. Exposure limit reached → increase gain.
 10. Signal above 80% + gain near unity → reduce exposure.
 11. Signal above 80% + exposure already short → reduce gain.
 12. Stop when target reached, limits hit, or cancelled.
 13. Store final accepted settings (handled by caller via returned result).

Dust-cap / no-signal detection (FR-AG-030):
  If mean_frac < 2% at max gain and ≥ 4 s exposure:
    - zero_clipped_pct > 50% → POSSIBLE_DUST_CAP (histogram looks like dark frame)
    - otherwise           → NO_SIGNAL
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from enum import Enum

import numpy as np

from ..ports.camera import CameraPort
from .autogain import AutoGainMode, _LO, _HI, _MAX_RATIO, _TARGET, _select_conversion_gain
from .camera_capabilities import ConversionGain
from .camera_profile import CameraProfile
from .histogram import HistogramStats, analyze as _hist_analyze
from .last_good_settings import LastGoodSettings
from .planet_detection import DetectedObject, detect_planet

_log = logging.getLogger(__name__)

# ── Tuning constants ──────────────────────────────────────────────────────────

_GAIN_MIN              = 100      # minimum camera gain (1× = 100 for ToupTek)
_NO_SIGNAL_EXP_MS      = 4_000.0  # exposure threshold for no-signal classification (DSO)
_NO_SIGNAL_THRESHOLD   = 0.02     # effective mean_frac below which we declare no signal
_FOCUS_ERROR_THRESHOLD = 0.001    # tiny-but-nonzero signal → focus/pointing issue
_SAT_LIMIT_PCT         = 1.0      # saturation_pct above which we must dim
_CLIP_THRESHOLD_PCT    = 1.0      # zero_clipped_pct above which offset needs raising
_OFFSET_STEP_ADU       = 100      # ADU increment when zero clipping detected
_OFFSET_MAX_ADU        = 2_000    # hard cap on offset

# Guiding-mode tuning — signal metric is p99_9 (guide-star peak)
_GUIDE_LO              = 0.20     # guide-star peak lower bound (FR-GUIDE-001)
_GUIDE_HI              = 0.80     # guide-star peak upper bound (saturation risk)
_GUIDE_TARGET          = 0.45     # midpoint
_GUIDE_NO_SIGNAL_THR   = 0.02     # p99_9 below this → no guide star detected

# Planetary-mode tuning — signal metric is detected planet's peak_frac
_PLANET_LO             = 0.40     # planet peak lower bound (FR-PLANET-001)
_PLANET_HI             = 0.80     # planet peak must not exceed this (FR-PLANET-003)
_PLANET_TARGET         = 0.60     # midpoint
_PLANET_NO_SIGNAL_THR  = 0.05     # peak below this → no planet detected


# ── Result types ──────────────────────────────────────────────────────────────

class AutoGainStatus(str, Enum):
    OK                               = "AUTO_GAIN_OK"
    NO_SIGNAL                        = "AUTO_GAIN_NO_SIGNAL"
    POSSIBLE_DUST_CAP                = "AUTO_GAIN_POSSIBLE_DUST_CAP"
    POSSIBLE_FOCUS_OR_POINTING_ERROR = "AUTO_GAIN_POSSIBLE_FOCUS_OR_POINTING_ERROR"
    EXPOSURE_LIMIT_REACHED           = "AUTO_GAIN_EXPOSURE_LIMIT_REACHED"
    GAIN_LIMIT_REACHED               = "AUTO_GAIN_GAIN_LIMIT_REACHED"
    CLIPPING_RISK                    = "AUTO_GAIN_CLIPPING_RISK"
    CANCELLED                        = "AUTO_GAIN_CANCELLED"
    UNSUPPORTED                      = "AUTO_GAIN_UNSUPPORTED"


@dataclass(frozen=True)
class AutoGainResult:
    """Outcome of a one-shot auto-gain run."""
    status: AutoGainStatus
    exposure_ms: float
    gain: int
    offset: int
    conversion_gain: ConversionGain
    histogram_stats: HistogramStats | None = None
    warning_msg: str | None = None


# ── Internal helpers ──────────────────────────────────────────────────────────

def _apply_settings(
    camera: CameraPort,
    exposure_ms: float,
    gain: int,
    offset: int,
) -> None:
    with _suppress():
        camera.set_gain(gain)
    with _suppress():
        camera.set_black_level(offset)
    with _suppress():
        camera.set_exposure_ms(exposure_ms)


class _suppress:
    """Context manager: silently suppress any exception."""
    def __enter__(self) -> _suppress:
        return self
    def __exit__(self, *_: object) -> bool:
        return True


def _effective_mean(stats: HistogramStats, offset: int, adc_max: float) -> float:
    offset_frac = offset / adc_max
    return max(0.0, stats.mean_frac - offset_frac)


# ── Service ───────────────────────────────────────────────────────────────────

class AutoGainService:
    """One-shot auto-gain adjustment following FR-AG-090."""

    @staticmethod
    def run_one_shot(
        camera: CameraPort,
        profile: CameraProfile,
        mode: AutoGainMode = AutoGainMode.DSO,
        last_good: LastGoodSettings | None = None,
        calibration_stats: HistogramStats | None = None,
        cancellation_flag: threading.Event | None = None,
        max_iterations: int = 12,
    ) -> AutoGainResult:
        """Capture and adjust until histogram is in target band or limits are reached.

        Args:
            camera:            Connected camera to read and control.
            profile:           CameraProfile providing gain/exposure limits.
            mode:              Auto-gain mode (DSO, PLANETARY, LUNAR, GUIDING).
            last_good:         Previous successful result to use as starting point.
            calibration_stats: HistogramStats from master bias for offset estimation.
            cancellation_flag: Set this Event to abort the loop (returns CANCELLED).
            max_iterations:    Safety cap on the number of capture–adjust cycles.

        Returns:
            AutoGainResult with the recommended settings and outcome status.
        """
        # Derive camera limits
        bit_depth = 16
        with _suppress():
            bit_depth = camera.get_bit_depth()
        adc_max = float((1 << bit_depth) - 1)

        gain_min  = _GAIN_MIN
        gain_max  = profile.max_gain
        exp_min_ms = profile.min_preview_exp_ms
        exp_max_ms = profile.max_preview_exp_ms

        # Step 2: conversion gain
        cg = _select_conversion_gain(profile, mode)
        with _suppress():
            camera.set_conversion_gain(cg)

        # Step 3: starting settings from last_good or profile defaults
        if last_good is not None:
            cur_exp_ms = float(np.clip(last_good.exposure_ms, exp_min_ms, exp_max_ms))
            cur_gain   = int(np.clip(last_good.gain, gain_min, gain_max))
            cur_offset = max(0, last_good.offset)
        else:
            cur_exp_ms = min(2_000.0, exp_max_ms)
            if cg == ConversionGain.HCG and profile.unity_gain_hcg is not None:
                cur_gain = int(np.clip(profile.unity_gain_hcg, gain_min, gain_max))
            elif profile.unity_gain_lcg is not None:
                cur_gain = int(np.clip(profile.unity_gain_lcg, gain_min, gain_max))
            else:
                cur_gain = gain_min
            cur_offset = 0

        # Step 4: offset from calibration bias stats when no last_good
        if calibration_stats is not None and last_good is None:
            suggested_offset = int(calibration_stats.black_level * adc_max)
            if suggested_offset > cur_offset:
                cur_offset = suggested_offset

        last_stats: HistogramStats | None = None
        last_detected: DetectedObject | None = None

        # Mode-specific parameters (FR-GUIDE-001, FR-PLANET-001)
        is_guiding   = (mode == AutoGainMode.GUIDING)
        is_planetary = (mode == AutoGainMode.PLANETARY)
        if is_guiding:
            band_lo, band_hi, band_tgt = _GUIDE_LO, _GUIDE_HI, _GUIDE_TARGET
            ns_signal_thr = _GUIDE_NO_SIGNAL_THR
            ns_exp_ms     = exp_max_ms   # classify no-signal at profile ceiling
        elif is_planetary:
            band_lo, band_hi, band_tgt = _PLANET_LO, _PLANET_HI, _PLANET_TARGET
            ns_signal_thr = _PLANET_NO_SIGNAL_THR
            ns_exp_ms     = exp_max_ms
        else:
            band_lo, band_hi, band_tgt = _LO, _HI, _TARGET
            ns_signal_thr = _NO_SIGNAL_THRESHOLD
            ns_exp_ms     = _NO_SIGNAL_EXP_MS

        # Steps 5–12: adjustment loop
        for iteration in range(max_iterations):
            # Cancellation check
            if cancellation_flag is not None and cancellation_flag.is_set():
                return AutoGainResult(
                    status=AutoGainStatus.CANCELLED,
                    exposure_ms=cur_exp_ms,
                    gain=cur_gain,
                    offset=cur_offset,
                    conversion_gain=cg,
                    histogram_stats=last_stats,
                )

            # Apply settings and capture
            _apply_settings(camera, cur_exp_ms, cur_gain, cur_offset)
            try:
                frame = camera.capture(cur_exp_ms / 1000.0)
            except Exception as exc:
                _log.error("AutoGain: capture failed at iteration %d: %s", iteration, exc)
                return AutoGainResult(
                    status=AutoGainStatus.UNSUPPORTED,
                    exposure_ms=cur_exp_ms,
                    gain=cur_gain,
                    offset=cur_offset,
                    conversion_gain=cg,
                    warning_msg=str(exc),
                )

            stats = _hist_analyze(frame.pixels, bit_depth=bit_depth)
            last_stats = stats
            eff_mean = _effective_mean(stats, cur_offset, adc_max)
            # Signal metric depends on mode:
            # - GUIDING: p99_9 (guide-star peak in dark field)
            # - PLANETARY: detected planet peak_frac (FR-PLANET-001)
            # - DSO/LUNAR: effective mean
            if is_guiding:
                signal = stats.p99_9
            elif is_planetary:
                last_detected = detect_planet(frame.pixels, bit_depth=bit_depth)
                signal = last_detected.peak_frac if last_detected is not None else eff_mean
            else:
                signal = eff_mean

            _log.info(
                "AutoGain iter %d/%d: exp=%.1fms gain=%d offset=%d "
                "mean=%.3f signal=%.3f sat=%.1f%% clip=%.1f%%",
                iteration + 1, max_iterations,
                cur_exp_ms, cur_gain, cur_offset,
                stats.mean_frac, signal, stats.saturation_pct, stats.zero_clipped_pct,
            )

            # Step 6: success check
            if band_lo <= signal <= band_hi and stats.saturation_pct < _SAT_LIMIT_PCT:
                _log.info(
                    "AutoGain OK after %d iterations: exp=%.1fms gain=%d offset=%d cg=%s",
                    iteration + 1, cur_exp_ms, cur_gain, cur_offset, cg.name,
                )
                return AutoGainResult(
                    status=AutoGainStatus.OK,
                    exposure_ms=cur_exp_ms,
                    gain=cur_gain,
                    offset=cur_offset,
                    conversion_gain=cg,
                    histogram_stats=stats,
                )

            # Proportional ratio toward target
            ratio = min(_MAX_RATIO, max(1.0 / _MAX_RATIO, band_tgt / max(signal, 1e-4)))

            # Step 7: zero-clipping → raise offset first (DSO only — guiding/planetary target peak)
            if (not is_guiding
                    and not is_planetary
                    and stats.zero_clipped_pct > _CLIP_THRESHOLD_PCT
                    and cur_offset < _OFFSET_MAX_ADU):
                new_offset = min(_OFFSET_MAX_ADU, cur_offset + _OFFSET_STEP_ADU)
                _log.info("AutoGain: zero-clipping %.1f%% — offset %d → %d",
                          stats.zero_clipped_pct, cur_offset, new_offset)
                cur_offset = new_offset
                continue

            if signal < band_lo:
                # Too dark: brighten
                at_exp_max  = cur_exp_ms >= exp_max_ms - 0.1
                at_gain_max = cur_gain >= gain_max

                if at_exp_max and at_gain_max:
                    # At all limits — classify no-signal
                    if signal < ns_signal_thr and cur_exp_ms >= ns_exp_ms:
                        if stats.zero_clipped_pct > 50.0:
                            return AutoGainResult(
                                status=AutoGainStatus.POSSIBLE_DUST_CAP,
                                exposure_ms=cur_exp_ms,
                                gain=cur_gain,
                                offset=cur_offset,
                                conversion_gain=cg,
                                histogram_stats=stats,
                                warning_msg="Histogram consistent with dark frame — check dust cap",
                            )
                        if not is_guiding and not is_planetary and eff_mean > _FOCUS_ERROR_THRESHOLD:
                            return AutoGainResult(
                                status=AutoGainStatus.POSSIBLE_FOCUS_OR_POINTING_ERROR,
                                exposure_ms=cur_exp_ms,
                                gain=cur_gain,
                                offset=cur_offset,
                                conversion_gain=cg,
                                histogram_stats=stats,
                                warning_msg="Faint signal detected — check focus and confirm mount is tracking",
                            )
                        if is_guiding:
                            no_signal_msg = (
                                "No guide star detected at maximum gain and exposure — "
                                "check guide scope focus and target field"
                            )
                        elif is_planetary:
                            no_signal_msg = (
                                "No planet detected at maximum gain and exposure — "
                                "ensure planet is in field of view"
                            )
                        else:
                            no_signal_msg = "No signal at maximum gain and 4 s exposure"
                        return AutoGainResult(
                            status=AutoGainStatus.NO_SIGNAL,
                            exposure_ms=cur_exp_ms,
                            gain=cur_gain,
                            offset=cur_offset,
                            conversion_gain=cg,
                            histogram_stats=stats,
                            warning_msg=no_signal_msg,
                        )
                    return AutoGainResult(
                        status=AutoGainStatus.GAIN_LIMIT_REACHED,
                        exposure_ms=cur_exp_ms,
                        gain=cur_gain,
                        offset=cur_offset,
                        conversion_gain=cg,
                        histogram_stats=stats,
                        warning_msg="Gain limit reached; target not reachable within profile limits",
                    )

                # Step 8: increase exposure
                if not at_exp_max:
                    new_exp = min(exp_max_ms, max(cur_exp_ms * ratio, cur_exp_ms + 1.0))
                    cur_exp_ms = new_exp
                # Step 9: increase gain when at exposure ceiling
                else:
                    new_gain = min(gain_max, max(int(cur_gain * ratio), cur_gain + 1))
                    cur_gain = new_gain

            else:
                # Too bright: dim
                at_exp_min  = cur_exp_ms <= exp_min_ms + 0.001
                at_gain_min = cur_gain <= gain_min

                if at_exp_min and at_gain_min:
                    return AutoGainResult(
                        status=AutoGainStatus.CLIPPING_RISK,
                        exposure_ms=cur_exp_ms,
                        gain=cur_gain,
                        offset=cur_offset,
                        conversion_gain=cg,
                        histogram_stats=stats,
                        warning_msg="Cannot reduce brightness further; saturation risk remains",
                    )

                # Step 10: reduce exposure first
                if not at_exp_min:
                    new_exp = max(exp_min_ms, min(cur_exp_ms * ratio, cur_exp_ms - 0.001))
                    cur_exp_ms = new_exp
                # Step 11: reduce gain when at exposure floor
                else:
                    new_gain = max(gain_min, min(int(cur_gain * ratio), cur_gain - 1))
                    cur_gain = new_gain

        # Loop exhausted without success
        if last_stats is not None:
            eff_mean_final = _effective_mean(last_stats, cur_offset, adc_max)
            if is_guiding:
                signal_final = last_stats.p99_9
            elif is_planetary and last_detected is not None:
                signal_final = last_detected.peak_frac
            else:
                signal_final = eff_mean_final
        else:
            signal_final = 0.0
        _log.warning(
            "AutoGain: loop exhausted (%d iterations), signal=%.3f",
            max_iterations, signal_final,
        )
        if signal_final > band_hi:
            return AutoGainResult(
                status=AutoGainStatus.CLIPPING_RISK,
                exposure_ms=cur_exp_ms,
                gain=cur_gain,
                offset=cur_offset,
                conversion_gain=cg,
                histogram_stats=last_stats,
            )
        if cur_gain >= gain_max:
            return AutoGainResult(
                status=AutoGainStatus.GAIN_LIMIT_REACHED,
                exposure_ms=cur_exp_ms,
                gain=cur_gain,
                offset=cur_offset,
                conversion_gain=cg,
                histogram_stats=last_stats,
            )
        return AutoGainResult(
            status=AutoGainStatus.EXPOSURE_LIMIT_REACHED,
            exposure_ms=cur_exp_ms,
            gain=cur_gain,
            offset=cur_offset,
            conversion_gain=cg,
            histogram_stats=last_stats,
        )
