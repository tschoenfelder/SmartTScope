"""Tests for the display stretch pipeline — Phase 3, Task 3.2."""
from __future__ import annotations

import numpy as np
import pytest

from smart_telescope.domain.collimation.processing.stretch import (
    auto_stretch,
    estimate_background,
    peak_location,
    saturation_fraction,
)


# ── estimate_background ───────────────────────────────────────────────────────

class TestEstimateBackground:
    def test_flat_frame(self):
        data = np.full((50, 50), 500.0, dtype=np.float32)
        bg, sigma = estimate_background(data)
        assert bg == pytest.approx(500.0, abs=1.0)
        assert sigma >= 1.0  # clamped floor

    def test_noisy_frame(self):
        rng = np.random.default_rng(42)
        data = rng.normal(loc=1000.0, scale=20.0, size=(100, 100)).astype(np.float32)
        bg, sigma = estimate_background(data)
        assert bg == pytest.approx(1000.0, abs=5.0)
        assert sigma == pytest.approx(20.0, rel=0.3)

    def test_bright_star_ignored(self):
        """Background estimator should not be pulled toward a bright star blob."""
        rng = np.random.default_rng(7)
        data = rng.normal(loc=500.0, scale=10.0, size=(100, 100)).astype(np.float32)
        # Insert a bright star (2 % of pixels at 10000 ADU)
        data[:5, :4] = 10000.0
        bg, _sigma = estimate_background(data)
        assert bg == pytest.approx(500.0, abs=15.0)

    def test_sigma_floor(self):
        data = np.full((10, 10), 100.0, dtype=np.float32)
        _bg, sigma = estimate_background(data)
        assert sigma >= 1.0

    def test_returns_tuple_of_floats(self):
        data = np.ones((5, 5), dtype=np.float32) * 42.0
        bg, sigma = estimate_background(data)
        assert isinstance(bg, float)
        assert isinstance(sigma, float)


# ── auto_stretch ──────────────────────────────────────────────────────────────

class TestAutoStretch:
    def test_output_dtype_uint8(self):
        data = np.arange(256, dtype=np.float32)
        result = auto_stretch(data)
        assert result.dtype == np.uint8

    def test_output_shape_preserved(self):
        data = np.ones((30, 40), dtype=np.float32) * 1000.0
        result = auto_stretch(data)
        assert result.shape == (30, 40)

    def test_range_is_0_255(self):
        data = np.linspace(0.0, 65535.0, 10000, dtype=np.float32)
        result = auto_stretch(data)
        assert int(result.min()) >= 0
        assert int(result.max()) <= 255

    def test_monotone_increasing(self):
        data = np.linspace(100.0, 60000.0, 500, dtype=np.float32)
        result = auto_stretch(data)
        assert np.all(np.diff(result.astype(np.int32)) >= 0)

    def test_flat_frame_does_not_crash(self):
        data = np.full((20, 20), 5000.0, dtype=np.float32)
        result = auto_stretch(data)
        assert result.shape == (20, 20)

    def test_does_not_mutate_input(self):
        data = np.linspace(0.0, 1000.0, 100, dtype=np.float32)
        original = data.copy()
        auto_stretch(data)
        assert np.array_equal(data, original)


# ── saturation_fraction ───────────────────────────────────────────────────────

class TestSaturationFraction:
    def test_fully_saturated(self):
        data = np.full((10, 10), 65535.0, dtype=np.float32)
        assert saturation_fraction(data, bit_depth=16) == pytest.approx(1.0)

    def test_fully_unsaturated(self):
        data = np.full((10, 10), 1000.0, dtype=np.float32)
        assert saturation_fraction(data, bit_depth=16) == pytest.approx(0.0)

    def test_half_saturated(self):
        data = np.zeros((10, 10), dtype=np.float32)
        data[:5, :] = 65535.0
        frac = saturation_fraction(data, bit_depth=16)
        assert frac == pytest.approx(0.5, abs=0.01)

    def test_8bit_threshold(self):
        data = np.array([200.0, 254.0, 255.0], dtype=np.float32)
        frac = saturation_fraction(data, bit_depth=8)
        assert frac == pytest.approx(2.0 / 3.0, abs=0.01)

    def test_returns_float(self):
        data = np.ones((5, 5), dtype=np.float32)
        result = saturation_fraction(data, bit_depth=16)
        assert isinstance(result, float)


# ── peak_location ─────────────────────────────────────────────────────────────

class TestPeakLocation:
    def test_finds_peak(self):
        data = np.zeros((20, 30), dtype=np.float32)
        data[10, 15] = 9999.0
        col, row, val = peak_location(data)
        assert col == pytest.approx(15.0)
        assert row == pytest.approx(10.0)
        assert val == pytest.approx(9999.0)

    def test_top_left(self):
        data = np.ones((10, 10), dtype=np.float32)
        data[0, 0] = 100.0
        col, row, val = peak_location(data)
        assert col == pytest.approx(0.0)
        assert row == pytest.approx(0.0)
