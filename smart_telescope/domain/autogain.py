"""Adaptive exposure / gain controller for display previews.

Keeps frames well-exposed without affecting raw-capture settings.
Target: mean signal in [_LO, _HI] fraction of the ADU range.
Strategy: adjust exposure first (up to 4 s), then gain (up to _GAIN_MAX).
"""

from __future__ import annotations

import numpy as np

_LO      = 0.12   # target lower bound (fraction of ADU range)
_HI      = 0.45   # target upper bound
_STEP    = 1.4    # multiplicative step size for adjustments
_EXP_MAX = 4.0    # seconds — hard cap (per requirements)
_EXP_MIN = 0.5
_GAIN_MIN = 100
_GAIN_MAX = 400


class AutoGainController:
    """Stateful controller that suggests the next (exposure, gain) after each frame.

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
        adc_max = float(np.iinfo(pixels.dtype).max) if np.issubdtype(pixels.dtype, np.integer) else 1.0
        mean_frac = float(np.mean(pixels)) / adc_max

        if mean_frac < _LO:
            # too dark — brighten
            if self.exposure < _EXP_MAX:
                self.exposure = min(_EXP_MAX, self.exposure * _STEP)
            elif self.gain < _GAIN_MAX:
                self.gain = min(_GAIN_MAX, int(self.gain * _STEP))
        elif mean_frac > _HI:
            # too bright — dim (exposure first, then gain)
            if self.exposure > _EXP_MIN:
                self.exposure = max(_EXP_MIN, self.exposure / _STEP)
            elif self.gain > _GAIN_MIN:
                self.gain = max(_GAIN_MIN, int(self.gain / _STEP))
