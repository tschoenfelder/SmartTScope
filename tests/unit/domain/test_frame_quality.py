"""Unit tests for the FrameQualityFilter domain object."""
from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from smart_telescope.domain.frame import FitsFrame
from smart_telescope.domain.frame_quality import (
    FrameQualityConfig,
    FrameQualityFilter,
    FrameQualityResult,
    _frame_snr,
)


# ── helpers ───────────────────────────────────────────────────────────────────


def _frame(pixels: np.ndarray) -> FitsFrame:  # type: ignore[type-arg]
    return FitsFrame(pixels=pixels, header={}, exposure_seconds=5.0, data=b"FAKE")


def _bright_frame(seed: int = 42) -> FitsFrame:
    """Noisy sky background (mean=100, std=10) with ~2% bright-star pixels (value ~1100).

    The 99.5th-percentile peak is clearly elevated above the background.
    """
    rng = np.random.default_rng(seed)
    pixels: np.ndarray[Any, np.dtype[Any]] = rng.normal(100.0, 10.0, (64, 64)).astype(np.float32)
    n_stars = 64 * 64 // 50  # ~2 % of pixels are stars
    ys = rng.integers(0, 64, size=n_stars)
    xs = rng.integers(0, 64, size=n_stars)
    pixels[ys, xs] += 1000.0
    return _frame(pixels)


def _dim_frame(seed: int = 99) -> FitsFrame:
    """Same noisy background but stars only 10% above sky (simulates cloud cover).

    SNR is ~20× lower than _bright_frame, well below the 0.3 threshold.
    """
    rng = np.random.default_rng(seed)
    pixels: np.ndarray[Any, np.dtype[Any]] = rng.normal(100.0, 10.0, (64, 64)).astype(np.float32)
    n_stars = 64 * 64 // 50
    ys = rng.integers(0, 64, size=n_stars)
    xs = rng.integers(0, 64, size=n_stars)
    pixels[ys, xs] += 10.0  # barely above noise floor
    return _frame(pixels)


def _make_filter(
    min_snr_factor: float = 0.3,
    baseline_frames: int = 3,
) -> FrameQualityFilter:
    return FrameQualityFilter(FrameQualityConfig(min_snr_factor, baseline_frames))


# ── FrameQualityConfig ────────────────────────────────────────────────────────


class TestFrameQualityConfig:
    def test_defaults(self) -> None:
        cfg = FrameQualityConfig()
        assert cfg.min_snr_factor == 0.3
        assert cfg.baseline_frames == 3

    def test_custom_values(self) -> None:
        cfg = FrameQualityConfig(min_snr_factor=0.5, baseline_frames=5)
        assert cfg.min_snr_factor == 0.5
        assert cfg.baseline_frames == 5

    def test_invalid_snr_factor_negative(self) -> None:
        with pytest.raises(ValueError):
            FrameQualityConfig(min_snr_factor=-0.1)

    def test_invalid_snr_factor_above_one(self) -> None:
        with pytest.raises(ValueError):
            FrameQualityConfig(min_snr_factor=1.1)

    def test_invalid_baseline_frames_zero(self) -> None:
        with pytest.raises(ValueError):
            FrameQualityConfig(baseline_frames=0)

    def test_boundary_snr_factor_zero(self) -> None:
        cfg = FrameQualityConfig(min_snr_factor=0.0)
        assert cfg.min_snr_factor == 0.0

    def test_boundary_snr_factor_one(self) -> None:
        cfg = FrameQualityConfig(min_snr_factor=1.0)
        assert cfg.min_snr_factor == 1.0


# ── _frame_snr ────────────────────────────────────────────────────────────────


class TestFrameSnr:
    def test_zero_frame_returns_zero(self) -> None:
        pixels = np.zeros((64, 64), dtype=np.float32)
        assert _frame_snr(pixels) == 0.0

    def test_uniform_frame_returns_zero(self) -> None:
        pixels = np.full((64, 64), 100.0, dtype=np.float32)
        assert _frame_snr(pixels) == 0.0

    def test_noisy_frame_with_stars_returns_positive_snr(self) -> None:
        assert _frame_snr(_bright_frame().pixels) > 0.0

    def test_brighter_stars_have_higher_snr(self) -> None:
        assert _frame_snr(_bright_frame().pixels) > _frame_snr(_dim_frame().pixels)


# ── Baseline building ─────────────────────────────────────────────────────────


class TestBaselineBuilding:
    def test_first_frames_always_accepted(self) -> None:
        f = _make_filter(min_snr_factor=0.9, baseline_frames=3)
        for _ in range(3):
            result = f.evaluate(_bright_frame())
            assert result.accepted is True

    def test_baseline_snr_none_during_warmup(self) -> None:
        f = _make_filter(baseline_frames=3)
        result = f.evaluate(_bright_frame())
        assert result.baseline_snr is None

    def test_baseline_snr_set_after_warmup(self) -> None:
        f = _make_filter(baseline_frames=2)
        f.evaluate(_bright_frame())
        f.evaluate(_bright_frame())
        result = f.evaluate(_bright_frame())
        assert result.baseline_snr is not None and result.baseline_snr > 0.0


# ── Acceptance ────────────────────────────────────────────────────────────────


class TestAcceptance:
    def _primed_filter(self, min_snr_factor: float = 0.3) -> FrameQualityFilter:
        """Return a filter that has already consumed its baseline frames."""
        f = _make_filter(min_snr_factor=min_snr_factor, baseline_frames=3)
        for i in range(3):
            f.evaluate(_bright_frame(seed=i))
        return f

    def test_bright_frame_accepted_after_baseline(self) -> None:
        f = self._primed_filter()
        result = f.evaluate(_bright_frame(seed=10))
        assert result.accepted is True
        assert result.reason is None

    def test_dim_frame_rejected_after_baseline(self) -> None:
        f = self._primed_filter(min_snr_factor=0.3)
        result = f.evaluate(_dim_frame())
        assert result.accepted is False
        assert result.reason is not None
        assert "SNR" in result.reason

    def test_rejected_result_includes_snr_values(self) -> None:
        f = self._primed_filter()
        result = f.evaluate(_dim_frame())
        assert result.snr >= 0.0
        assert result.baseline_snr is not None and result.baseline_snr > 0.0

    def test_disabled_filter_accepts_dim_frame(self) -> None:
        f = _make_filter(min_snr_factor=0.0, baseline_frames=3)
        for i in range(3):
            f.evaluate(_bright_frame(seed=i))
        result = f.evaluate(_dim_frame())
        assert result.accepted is True

    def test_accepted_frame_updates_baseline(self) -> None:
        """SNR history rolls: accepted frames enter the deque, rejected ones do not."""
        f = _make_filter(min_snr_factor=0.3, baseline_frames=2)
        for i in range(4):
            result = f.evaluate(_bright_frame(seed=i))
        assert result.accepted is True

    def test_rejected_frame_does_not_update_baseline(self) -> None:
        f = _make_filter(min_snr_factor=0.3, baseline_frames=3)
        for i in range(3):
            f.evaluate(_bright_frame(seed=i))
        dim_result = f.evaluate(_dim_frame())
        assert dim_result.accepted is False
        # After a reject, the next bright frame should still be accepted
        bright_result = f.evaluate(_bright_frame(seed=50))
        assert bright_result.accepted is True
