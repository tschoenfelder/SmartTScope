"""Adaptive exposure / gain controller for display previews.

Keeps frames well-exposed without affecting raw-capture settings.
Target: mean signal in [_LO, _HI] fraction of the ADU range.
Strategy: proportional control — scale exposure by (target/mean), capped
at 8× per step.  Adjust exposure first (up to 4 s), then gain.
"""

from __future__ import annotations

import numpy as np

_LO      = 0.12   # target lower bound (fraction of ADU range)
_HI      = 0.45   # target upper bound
_TARGET  = (_LO + _HI) / 2.0   # 0.285 — aim for midpoint of band
_MAX_RATIO = 8.0  # largest single-step change factor (either direction)
_EXP_MAX = 4.0    # seconds — hard cap
_EXP_MIN = 0.001  # 1 ms — minimum; allows guide cameras to converge
_GAIN_MIN = 100
_GAIN_MAX = 400


class AutoGainController:
    """Stateful controller that suggests the next (exposure, gain) after each frame.

    Uses a proportional control law: the exposure is scaled by
    (target_mean / measured_mean), capped to 8× per step so a single
    saturated or black frame causes a large but bounded correction.
    This converges in 1–2 frames vs the old fixed-step approach that
    needed 6+ frames and caused sustained oscillation.

    Usage::

        ctrl = AutoGainController()
        while True:
            frame = camera.capture(ctrl.exposure)
            yield frame
            ctrl.update(frame.pixels)
    """

    def __init__(self, exposure: float = 2.0, gain: int = _GAIN_MIN) -> None:
        self.exposure = float(max(_EXP_MIN, min(_EXP_MAX, exposure)))
        self.gain     = int(max(_GAIN_MIN, min(_GAIN_MAX, gain)))

    def update(self, pixels: np.ndarray) -> None:  # type: ignore[type-arg]
        """Inspect *pixels* and adjust (exposure, gain) for the next capture."""
        if np.issubdtype(pixels.dtype, np.integer):
            adc_max = float(np.iinfo(pixels.dtype).max)
        elif float(np.max(pixels)) > 1.0:
            # float32 from camera: uint16 values cast to float — use 16-bit max
            adc_max = 65535.0
        else:
            adc_max = 1.0
        mean_frac = float(np.mean(pixels)) / adc_max

        if _LO <= mean_frac <= _HI:
            return  # already in target band — no change

        # Proportional ratio: how much to scale exposure toward _TARGET.
        # Capped to [1/_MAX_RATIO, _MAX_RATIO] to prevent wild single-step jumps.
        safe_mean = max(mean_frac, 1e-4)
        ratio = min(_MAX_RATIO, max(1.0 / _MAX_RATIO, _TARGET / safe_mean))

        if mean_frac < _LO:
            # too dark — brighten exposure first, then gain
            new_exp = min(_EXP_MAX, self.exposure * ratio)
            if new_exp > self.exposure:
                self.exposure = new_exp
            elif self.gain < _GAIN_MAX:
                self.gain = min(_GAIN_MAX, int(self.gain * ratio))
        else:
            # too bright — dim exposure first, then gain
            new_exp = max(_EXP_MIN, self.exposure * ratio)
            if new_exp < self.exposure:
                self.exposure = new_exp
            elif self.gain > _GAIN_MIN:
                self.gain = max(_GAIN_MIN, int(self.gain * ratio))
