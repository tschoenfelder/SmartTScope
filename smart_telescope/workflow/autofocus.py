"""Autofocus sweep — moves the focuser across a range, measures sharpness at each
position via Laplacian variance, fits a parabola, and returns the best position.

The caller is responsible for connecting the focuser and camera before calling
run_autofocus(), and for restoring the original position on failure if desired.
"""

from __future__ import annotations

import time
from collections.abc import Callable

import numpy as np

from ..domain.autofocus import AutofocusParams, AutofocusResult
from ..domain.focus_metric import half_flux_diameter
from ..ports.camera import CameraPort
from ..ports.focuser import FocuserPort

_SETTLE_POLL_S   = 0.1   # poll interval while waiting for focuser to stop
_SETTLE_TIMEOUT  = 30.0  # max wait for focuser to stop after a move

ProgressCallback = Callable[[int, int, float], None]  # (position, sample_idx, metric)


def run_autofocus(
    focuser: FocuserPort,
    camera:  CameraPort,
    params:  AutofocusParams,
    *,
    progress: ProgressCallback | None = None,
) -> AutofocusResult:
    """Sweep the focuser, capture a frame at each stop, and find the sharpest position.

    Returns an AutofocusResult.  On failure the focuser is left at the last
    attempted position; the caller should move it back to start_position if needed.

    Raises RuntimeError if fewer than 3 positions were sampled successfully
    (not enough to fit a parabola or find a meaningful peak).
    """
    start_pos = focuser.get_position()
    half = params.range_steps // 2
    sweep_start = start_pos - half
    sweep_end   = start_pos + half

    positions: list[int] = list(
        range(sweep_start, sweep_end + params.step_size, params.step_size)
    )

    sampled_pos:     list[int]   = []
    sampled_metrics: list[float] = []

    for idx, pos in enumerate(positions):
        focuser.move(pos)
        _wait_stopped(focuser)

        frame = camera.capture(params.exposure)
        metric = half_flux_diameter(frame.pixels)

        sampled_pos.append(pos)
        sampled_metrics.append(metric)

        if progress is not None:
            progress(pos, idx, metric)

    if len(sampled_pos) < 3:
        raise RuntimeError(
            f"Autofocus needs at least 3 samples; only {len(sampled_pos)} succeeded"
        )

    best_idx, best_pos, fitted = _find_valley(sampled_pos, sampled_metrics)

    start_metric = sampled_metrics[0] if sampled_metrics else 1.0
    best_metric  = sampled_metrics[best_idx]
    # HFD is minimised at focus; gain = start / best (> 1 means improvement)
    gain = start_metric / best_metric if best_metric > 0 else 1.0

    focuser.move(best_pos)
    _wait_stopped(focuser)

    return AutofocusResult(
        best_position  = best_pos,
        start_position = start_pos,
        positions      = sampled_pos,
        metrics        = sampled_metrics,
        fitted         = fitted,
        metric_gain    = gain,
    )


# ── private helpers ───────────────────────────────────────────────────────────


def _wait_stopped(focuser: FocuserPort) -> None:
    elapsed = 0.0
    while focuser.is_moving():
        time.sleep(_SETTLE_POLL_S)
        elapsed += _SETTLE_POLL_S
        if elapsed >= _SETTLE_TIMEOUT:
            break  # proceed anyway; metric may be blurred but we don't abort


def _find_valley(
    positions: list[int],
    metrics:   list[float],
) -> tuple[int, int, bool]:
    """Return (best_idx, best_focuser_position, parabola_fit_succeeded).

    HFD is minimised at focus, so we fit an upward-opening parabola and
    return its vertex.  Falls back to argmin when the fit is invalid.
    """
    x = np.array(positions, dtype=float)
    y = np.array(metrics,   dtype=float)

    try:
        coeffs = np.polyfit(x, y, 2)
        a, b = coeffs[0], coeffs[1]
        if a > 0:  # upward-opening parabola — valid HFD curve shape
            vertex_x = -b / (2 * a)
            vertex_x = float(np.clip(vertex_x, x[0], x[-1]))
            best_idx = int(np.argmin(np.abs(x - vertex_x)))
            return best_idx, int(round(vertex_x)), True
    except (np.linalg.LinAlgError, ValueError):
        pass

    # Fall back to argmin
    best_idx = int(np.argmin(y))
    return best_idx, positions[best_idx], False
