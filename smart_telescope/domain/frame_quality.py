"""Frame quality filtering — reject frames that fall below a SNR threshold.

Computes a signal-to-noise ratio per frame and rejects frames where SNR drops
significantly below the running baseline (e.g., cloud passes, wind shake).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np

from .frame import FitsFrame


@dataclass
class FrameQualityConfig:
    min_snr_factor: float = 0.3  # reject if SNR < baseline * factor; 0.0 = accept all
    baseline_frames: int = 3     # frames used to build the initial SNR baseline

    def __post_init__(self) -> None:
        if not 0.0 <= self.min_snr_factor <= 1.0:
            raise ValueError("min_snr_factor must be in [0.0, 1.0]")
        if self.baseline_frames < 1:
            raise ValueError("baseline_frames must be >= 1")


@dataclass
class FrameQualityResult:
    accepted: bool
    snr: float
    baseline_snr: float | None = None
    reason: str | None = None  # set only when rejected


class FrameQualityFilter:
    """Stateful frame quality gate.

    The first *baseline_frames* accepted frames always pass and are used to
    establish a running SNR baseline (rolling median of the last baseline_frames
    accepted SNR values).  Subsequent frames are rejected when their SNR falls
    below *baseline_snr × min_snr_factor*.
    """

    def __init__(self, config: FrameQualityConfig) -> None:
        self._config = config
        self._snr_history: deque[float] = deque(maxlen=config.baseline_frames)

    def evaluate(self, frame: FitsFrame) -> FrameQualityResult:
        snr = _frame_snr(frame.pixels)

        # Still building baseline — accept unconditionally
        if len(self._snr_history) < self._config.baseline_frames:
            self._snr_history.append(snr)
            return FrameQualityResult(accepted=True, snr=snr)

        baseline_snr = float(np.median(list(self._snr_history)))

        threshold = baseline_snr * self._config.min_snr_factor
        if self._config.min_snr_factor > 0.0 and snr < threshold:
            return FrameQualityResult(
                accepted=False,
                snr=snr,
                baseline_snr=baseline_snr,
                reason=(
                    f"SNR {snr:.1f} < {self._config.min_snr_factor:.0%} "
                    f"of baseline {baseline_snr:.1f}"
                ),
            )

        self._snr_history.append(snr)
        return FrameQualityResult(accepted=True, snr=snr, baseline_snr=baseline_snr)


# ── Private helpers ──────────────────────────────────────────────────────────


def _frame_snr(pixels: np.ndarray) -> float:  # type: ignore[type-arg]
    """Estimate frame SNR using a robust sky-background model.

    SNR = (99.5th-percentile signal − sky_median) / sky_MAD

    Using the 99.5th percentile captures bright stars without being sensitive
    to the exact number of stars in the field.  The median absolute deviation
    (MAD) of the background is a robust noise estimator that ignores stars.
    """
    flat = pixels.ravel().astype(np.float32)
    sky = float(np.median(flat))
    noise = float(np.median(np.abs(flat - sky))) + 1e-9
    peak = float(np.percentile(flat, 99.5))
    return max((peak - sky) / noise, 0.0)
