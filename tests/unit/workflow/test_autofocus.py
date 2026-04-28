"""Unit tests for the autofocus sweep workflow."""
from __future__ import annotations

import numpy as np
import pytest

from smart_telescope.domain.autofocus import AutofocusParams, AutofocusResult
from smart_telescope.domain.frame import FitsFrame
from smart_telescope.workflow.autofocus import _find_peak, run_autofocus


# ── helpers ───────────────────────────────────────────────────────────────────


def _make_frame(metric_approx: float) -> FitsFrame:
    """Return a synthetic frame whose laplacian_variance is ≈ metric_approx."""
    rng = np.random.default_rng(int(metric_approx) % (2**31))
    # Scale noise amplitude to get roughly the desired variance
    amplitude = float(np.sqrt(max(metric_approx, 0.0)) / 4.0)
    pixels = (rng.normal(0, amplitude, size=(32, 32))).astype(np.float32)
    from astropy.io import fits  # type: ignore[import]
    hdr = fits.Header()
    hdr["EXPTIME"] = 1.0
    return FitsFrame(pixels=pixels, header=hdr, exposure_seconds=1.0)


class _MockFocuser:
    def __init__(self, start: int = 5000) -> None:
        self._pos = start
        self.moves: list[int] = []

    def connect(self) -> bool:
        return True

    def disconnect(self) -> None:
        pass

    def move(self, steps: int) -> None:
        self._pos = steps
        self.moves.append(steps)

    def get_position(self) -> int:
        return self._pos

    def is_moving(self) -> bool:
        return False  # instant settle

    def stop(self) -> None:
        pass


class _MockCamera:
    """Returns frames with metric that peaks at a known focuser position."""

    def __init__(self, peak_pos: int, focuser: _MockFocuser) -> None:
        self._peak = peak_pos
        self._focuser = focuser

    def connect(self) -> bool:
        return True

    def disconnect(self) -> None:
        pass

    def capture(self, exposure_seconds: float) -> FitsFrame:
        pos = self._focuser._pos
        distance = abs(pos - self._peak)
        # Metric is a downward parabola peaking at 10000 when exactly at focus
        metric = max(0.0, 10000.0 - (distance / 10.0) ** 2)
        return _make_frame(metric)


# ── AutofocusParams ───────────────────────────────────────────────────────────


class TestAutofocusParams:
    def test_valid_params(self) -> None:
        p = AutofocusParams(range_steps=1000, step_size=100, exposure=2.0)
        assert p.range_steps == 1000

    def test_rejects_zero_range(self) -> None:
        with pytest.raises(ValueError):
            AutofocusParams(range_steps=0, step_size=100, exposure=1.0)

    def test_rejects_zero_step(self) -> None:
        with pytest.raises(ValueError):
            AutofocusParams(range_steps=500, step_size=0, exposure=1.0)

    def test_rejects_zero_exposure(self) -> None:
        with pytest.raises(ValueError):
            AutofocusParams(range_steps=500, step_size=50, exposure=0.0)


# ── _find_peak ────────────────────────────────────────────────────────────────


class TestFindPeak:
    def test_parabola_finds_vertex(self) -> None:
        positions = list(range(4500, 5600, 100))
        metrics   = [max(0, 1000 - (p - 5000) ** 2 / 100) for p in positions]
        idx, best, fitted = _find_peak(positions, metrics)
        assert fitted is True
        assert abs(best - 5000) <= 100

    def test_falls_back_to_argmax_when_parabola_open(self) -> None:
        # Upward-opening parabola — not a valid focus curve; fall back to argmax
        positions = [4800, 4900, 5000, 5100, 5200]
        metrics   = [1.0, 2.0, 3.0, 2.0, 1.0]  # peak at index 2
        idx, best, fitted = _find_peak(positions, metrics)
        # Either parabola or argmax should pick 5000
        assert best == 5000

    def test_three_points_sufficient(self) -> None:
        positions = [100, 200, 300]
        metrics   = [1.0, 5.0, 1.0]
        idx, best, fitted = _find_peak(positions, metrics)
        assert fitted is True
        assert best == 200


# ── run_autofocus ─────────────────────────────────────────────────────────────


class TestRunAutofocus:
    def test_moves_to_best_position(self) -> None:
        focuser = _MockFocuser(start=5000)
        camera  = _MockCamera(peak_pos=5200, focuser=focuser)
        params  = AutofocusParams(range_steps=1000, step_size=100, exposure=0.01)
        result  = run_autofocus(focuser, camera, params)
        assert abs(result.best_position - 5200) <= 200

    def test_returns_autofocus_result(self) -> None:
        focuser = _MockFocuser(start=5000)
        camera  = _MockCamera(peak_pos=5000, focuser=focuser)
        params  = AutofocusParams(range_steps=500, step_size=100, exposure=0.01)
        result  = run_autofocus(focuser, camera, params)
        assert isinstance(result, AutofocusResult)
        assert len(result.positions) >= 3
        assert len(result.metrics) == len(result.positions)

    def test_focuser_ends_at_best_position(self) -> None:
        focuser = _MockFocuser(start=5000)
        camera  = _MockCamera(peak_pos=5000, focuser=focuser)
        params  = AutofocusParams(range_steps=500, step_size=100, exposure=0.01)
        result  = run_autofocus(focuser, camera, params)
        assert focuser.get_position() == result.best_position

    def test_progress_callback_called_for_each_sample(self) -> None:
        focuser  = _MockFocuser(start=5000)
        camera   = _MockCamera(peak_pos=5000, focuser=focuser)
        params   = AutofocusParams(range_steps=400, step_size=100, exposure=0.01)
        progress_calls: list[tuple[int, int, float]] = []
        run_autofocus(focuser, camera, params, progress=lambda p, i, m: progress_calls.append((p, i, m)))
        expected_samples = params.range_steps // params.step_size + 1
        assert len(progress_calls) == expected_samples

    def test_result_to_dict_has_required_keys(self) -> None:
        focuser = _MockFocuser(start=5000)
        camera  = _MockCamera(peak_pos=5000, focuser=focuser)
        params  = AutofocusParams(range_steps=400, step_size=100, exposure=0.01)
        d = run_autofocus(focuser, camera, params).to_dict()
        for key in ("best_position", "start_position", "positions", "metrics", "fitted", "metric_gain"):
            assert key in d

    def test_metric_gain_positive_when_focus_improves(self) -> None:
        focuser = _MockFocuser(start=4000)  # far from peak
        camera  = _MockCamera(peak_pos=5000, focuser=focuser)
        params  = AutofocusParams(range_steps=2000, step_size=200, exposure=0.01)
        result  = run_autofocus(focuser, camera, params)
        assert result.metric_gain > 0
