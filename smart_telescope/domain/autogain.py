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


# ── Conversion-gain mode ──────────────────────────────────────────────────────

class AutoGainMode(str, Enum):
    DSO       = "DSO"        # deep-sky: HCG preferred
    PLANETARY = "PLANETARY"  # planets/lunar: LCG preferred
    LUNAR     = "LUNAR"      # same policy as PLANETARY
    GUIDING   = "GUIDING"    # guide star: HCG preferred


def _select_conversion_gain(
    profile: CameraProfile | None,
    mode: AutoGainMode,
) -> ConversionGain:
    """Return the recommended conversion gain per FR-AG-080.

    DSO / GUIDING → HCG when available; otherwise LCG.
    PLANETARY / LUNAR → LCG when available; otherwise LCG (no HCG needed).
    """
    if profile is None:
        return ConversionGain.LCG
    if mode in (AutoGainMode.DSO, AutoGainMode.GUIDING):
        if profile.unity_gain_hcg is not None:
            return ConversionGain.HCG
    if profile.unity_gain_lcg is not None:
        return ConversionGain.LCG
    return ConversionGain.LCG  # safe fallback


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

        self.exposure = float(max(exp_min, min(exp_max, exposure)))
        self.gain     = int(max(gain_min, min(gain_max, gain)))
        self.conversion_gain: ConversionGain = _select_conversion_gain(profile, mode)

    def update(self, pixels: np.ndarray[Any, np.dtype[Any]]) -> None:  # type: ignore[type-arg]
        """Inspect *pixels* and adjust (exposure, gain) for the next capture.

        Uses HistogramStats with the declared bit depth for correct normalisation,
        then subtracts the offset_adu pedestal from the measured mean before
        comparing to the target band.
        """
        stats = _hist_analyze(pixels, bit_depth=self._bit_depth)
        adc_max = float((1 << self._bit_depth) - 1)
        offset_frac = self._offset_adu / adc_max
        mean_frac = max(0.0, stats.mean_frac - offset_frac)

        if _LO <= mean_frac <= _HI:
            return  # already in target band — no change

        safe_mean = max(mean_frac, 1e-4)
        ratio = min(_MAX_RATIO, max(1.0 / _MAX_RATIO, _TARGET / safe_mean))

        if mean_frac < _LO:
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
