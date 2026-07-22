"""Adaptive exposure / gain controller for display previews and one-shot auto gain.

Proportional control: scale exposure by (target_mean / measured_mean), capped
at 8× per step so a single saturated or black frame causes a large but bounded
correction.  Converges in 1–2 frames for most scenes.

When a *CameraProfile* is supplied the controller derives its limits from the
profile instead of built-in defaults, and selects the recommended conversion
gain for the requested mode (FR-AG-080).  Without a profile the controller
falls back to the previous hardcoded defaults so existing WebSocket autogain
callers require no changes.

Offset-aware histogram: the *offset_adu* argument shifts the baseline so that
a pedestal set by the camera's black-level control does not fool the algorithm
into thinking there is real signal (FR-AG-070).
"""

from __future__ import annotations

from enum import Enum
from typing import Any

import numpy as np

from .camera_capabilities import ConversionGain
from .camera_profile import CameraProfile
from .histogram import analyze as _hist_analyze

# ── Defaults (used when no CameraProfile is supplied) ─────────────────────────

_LO        = 0.12   # target lower bound (fraction of ADC range)
_HI        = 0.45   # target upper bound
_TARGET    = (_LO + _HI) / 2.0   # 0.285
_MAX_RATIO = 8.0    # largest single-step change factor

_GAIN_MIN  = 100
_GAIN_MAX  = 400
_EXP_MAX   = 4.0    # seconds
_EXP_MIN   = 0.001  # 1 ms
_SPARSE_P99_9_THR = 0.10  # p99_9 above this → stars present; halt brightening for sparse fields

# Guiding-mode tuning — signal metric is p99_9 (guide-star peak), not mean_frac.
# A guide camera stares at a mostly-dark sparse field; the mean stays near zero
# regardless of how well-exposed the one guide star is, so a mean-based target
# (as used for DSO) never reaches band and drives exposure/gain to their
# ceiling forever. Mirrors AutoGainService.run_one_shot()'s GUIDING band
# (domain/autogain_service.py) — kept in sync manually since the one-shot
# service imports its DSO constants from this module already.
_GUIDE_LO     = 0.20   # guide-star peak lower bound
_GUIDE_HI     = 0.80   # guide-star peak upper bound (saturation risk)
_GUIDE_TARGET = 0.45   # midpoint


# ── Conversion-gain mode ──────────────────────────────────────────────────────

class AutoGainMode(str, Enum):
    # M8-022 purpose modes
    PLATE_SOLVE = "PLATE_SOLVE"  # low offset; exposure capped by tracking quality (blur metric)
    DSO         = "DSO"          # deep-sky: HCG preferred
    PLANET      = "PLANET"       # planet/lunar: LCG preferred, peak-metric signal
    MOON        = "MOON"         # same policy as PLANET
    COLLIMATION = "COLLIMATION"  # defocus-donut: brightness-optimised, DSO behavior
    AUTOFOCUS   = "AUTOFOCUS"    # star FWHM focus: brightness-optimised, DSO behavior
    # backward-compatible names kept for existing callers
    PLANETARY   = "PLANETARY"    # alias for PLANET behavior
    LUNAR       = "LUNAR"        # alias for MOON/PLANET behavior
    GUIDING     = "GUIDING"      # guide-star: HCG preferred


_HCG_MODES = {
    AutoGainMode.DSO, AutoGainMode.GUIDING,
    AutoGainMode.PLATE_SOLVE, AutoGainMode.COLLIMATION, AutoGainMode.AUTOFOCUS,
}

_PLANET_MODES = {
    AutoGainMode.PLANET, AutoGainMode.MOON,
    AutoGainMode.PLANETARY, AutoGainMode.LUNAR,
}


def _select_conversion_gain(
    profile: CameraProfile | None,
    mode: AutoGainMode,
) -> ConversionGain:
    """Return the recommended conversion gain per FR-AG-080.

    DSO / GUIDING / PLATE_SOLVE / COLLIMATION / AUTOFOCUS → HCG when available.
    PLANET / MOON / PLANETARY / LUNAR → LCG.
    """
    if profile is None:
        return ConversionGain.LCG
    if mode in _HCG_MODES and profile.unity_gain_hcg is not None:
        return ConversionGain.HCG
    if profile.unity_gain_lcg is not None:
        return ConversionGain.LCG
    return ConversionGain.LCG  # safe fallback


def measure_elongation_ratio(pixels: "np.ndarray") -> float:  # type: ignore[type-arg]
    """Return gradient-anisotropy ratio as a star-trailing proxy.

    Compares mean absolute gradient energy in the horizontal vs vertical
    direction.  Ratio > 2.0 indicates significant elongation in one axis
    (typical RA trailing).  Ratio near 1.0 means stars are round.  Returns
    1.0 for uniform frames (no gradients in either axis → no elongation).

    Used by PLATE_SOLVE mode to cap exposure when tracking degrades.
    """
    px = pixels.astype(np.float32)
    g_x = float(np.abs(np.diff(px, axis=1)).mean())
    g_y = float(np.abs(np.diff(px, axis=0)).mean())
    if g_x < 1e-6 and g_y < 1e-6:
        return 1.0  # no gradients → uniform frame → no elongation detected
    lo = min(g_x, g_y) + 1e-6
    hi = max(g_x, g_y)
    return hi / lo


# ── Controller ────────────────────────────────────────────────────────────────

class AutoGainController:
    """Stateful proportional controller that adjusts (exposure, gain) after each frame.

    Args:
        exposure:    Initial exposure in seconds.
        gain:        Initial analog gain (camera units, typically 100–3200).
        profile:     CameraProfile to derive limits and conversion-gain policy.
                     When None the legacy hardcoded defaults are used.
        mode:        Capture mode; selects initial conversion gain per FR-AG-080.
        offset_adu:  Camera black-level setting in ADU.  The controller subtracts
                     this from the measured mean before comparing to target bounds,
                     so a non-zero pedestal is not mistaken for sky signal.
        bit_depth:   Effective ADC bit depth (e.g. 12 for a 12-bit sensor).
                     Used to normalise pixel values correctly via HistogramStats.

    Attributes:
        exposure:         Current recommended exposure in seconds.
        gain:             Current recommended gain.
        conversion_gain:  Recommended conversion-gain mode (set at init, not updated).
    """

    def __init__(
        self,
        exposure: float = 2.0,
        gain: int = _GAIN_MIN,
        profile: CameraProfile | None = None,
        mode: AutoGainMode = AutoGainMode.DSO,
        offset_adu: int = 0,
        bit_depth: int = 16,
    ) -> None:
        if profile is not None:
            gain_min: int = _GAIN_MIN
            gain_max: int = profile.max_gain
            exp_min: float = profile.min_preview_exp_ms / 1000.0
            exp_max: float = profile.max_preview_exp_ms / 1000.0
        else:
            gain_min = _GAIN_MIN
            gain_max = _GAIN_MAX
            exp_min  = _EXP_MIN
            exp_max  = _EXP_MAX

        self._gain_min  = gain_min
        self._gain_max  = gain_max
        self._exp_min   = exp_min
        self._exp_max   = exp_max
        self._offset_adu = int(max(0, offset_adu))
        self._bit_depth  = int(bit_depth)
        self._is_guiding = (mode == AutoGainMode.GUIDING)

        self.exposure = float(max(exp_min, min(exp_max, exposure)))
        self.gain     = int(max(gain_min, min(gain_max, gain)))
        self.conversion_gain: ConversionGain = _select_conversion_gain(profile, mode)

    def update(
        self,
        pixels: np.ndarray[Any, np.dtype[Any]],  # type: ignore[type-arg]
        bit_depth: int | None = None,
    ) -> None:
        """Inspect *pixels* and adjust (exposure, gain) for the next capture.

        Uses HistogramStats with the declared bit depth for correct normalisation,
        then subtracts the offset_adu pedestal from the measured mean before
        comparing to the target band.

        bit_depth: per-frame ADC depth (e.g. read fresh from the FITS header),
        overriding the value fixed at construction. Needed because callers may
        have to construct the controller before the first frame is captured —
        CameraPort.get_bit_depth() documents returning a default (16) until
        then for adapters that lazily detect the sensor's true native depth —
        so a value fixed at construction can stay wrong for the whole session.
        """
        if bit_depth is not None:
            self._bit_depth = int(bit_depth)
        stats = _hist_analyze(pixels, bit_depth=self._bit_depth)

        if self._is_guiding:
            # Guide-star peak, not mean — a guide camera stares at a mostly
            # dark sparse field, so mean_frac stays near zero regardless of
            # how well-exposed the one guide star is (see _GUIDE_LO comment).
            signal = stats.p99_9
            band_lo, band_hi, band_tgt = _GUIDE_LO, _GUIDE_HI, _GUIDE_TARGET
        else:
            adc_max = float((1 << self._bit_depth) - 1)
            offset_frac = self._offset_adu / adc_max
            signal = max(0.0, stats.mean_frac - offset_frac)
            band_lo, band_hi, band_tgt = _LO, _HI, _TARGET

        if band_lo <= signal <= band_hi:
            return  # already in target band — no change

        # Sparse star field (DSO only — GUIDING already targets the star peak
        # directly): if top 0.1% of pixels show star signal, don't over-brighten.
        if (not self._is_guiding and signal < band_lo
                and stats.p99_9 >= _SPARSE_P99_9_THR and stats.saturation_pct < 1.0):
            return

        safe_signal = max(signal, 1e-4)
        ratio = min(_MAX_RATIO, max(1.0 / _MAX_RATIO, band_tgt / safe_signal))

        if signal < band_lo:
            # too dark — brighten exposure first, then gain
            new_exp = min(self._exp_max, self.exposure * ratio)
            if new_exp > self.exposure:
                self.exposure = new_exp
            elif self.gain < self._gain_max:
                self.gain = min(self._gain_max, int(self.gain * ratio))
        else:
            # too bright — dim exposure first, then gain
            new_exp = max(self._exp_min, self.exposure * ratio)
            if new_exp < self.exposure:
                self.exposure = new_exp
            elif self.gain > self._gain_min:
                self.gain = max(self._gain_min, int(self.gain * ratio))
