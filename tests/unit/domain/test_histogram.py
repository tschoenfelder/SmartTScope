"""Unit tests for domain/histogram.py (AGT-2-1)."""
from __future__ import annotations

import numpy as np
import pytest

from smart_telescope.domain.histogram import HistogramStats, analyze, histogram_bins


def _uniform(value: float, shape: tuple[int, int] = (64, 64), dtype: type = np.float32) -> np.ndarray:
    return np.full(shape, value, dtype=dtype)


def _ramp(shape: tuple[int, int] = (64, 64), bit_depth: int = 12) -> np.ndarray:
    """Array covering [0, adc_max] linearly."""
    total = shape[0] * shape[1]
    adc_max = (1 << bit_depth) - 1
    return np.linspace(0, adc_max, total, dtype=np.float32).reshape(shape)


# ── HistogramStats fields ──────────────────────────────────────────────────────

class TestAnalyze:
    def test_returns_histogram_stats(self) -> None:
        arr = _uniform(1000.0)
        result = analyze(arr, bit_depth=12)
        assert isinstance(result, HistogramStats)

    def test_uniform_frame_p50_equals_mean(self) -> None:
        arr = _uniform(2047.0)
        s = analyze(arr, bit_depth=12)
        assert abs(s.p50 - s.mean_frac) < 1e-6

    def test_uniform_midrange_values(self) -> None:
        adc_max = (1 << 12) - 1
        arr = _uniform(adc_max / 2)
        s = analyze(arr, bit_depth=12)
        assert abs(s.p50 - 0.5) < 0.01
        assert abs(s.mean_frac - 0.5) < 0.01

    def test_zero_frame_all_zeros(self) -> None:
        arr = _uniform(0.0)
        s = analyze(arr, bit_depth=12)
        assert s.p50 == 0.0
        assert s.mean_frac == 0.0
        assert s.zero_clipped_pct == pytest.approx(100.0)
        assert s.saturation_pct == 0.0

    def test_saturated_frame(self) -> None:
        adc_max = (1 << 12) - 1
        arr = _uniform(adc_max)
        s = analyze(arr, bit_depth=12)
        assert s.p99 == pytest.approx(1.0, abs=1e-6)
        assert s.saturation_pct == pytest.approx(100.0)
        assert s.zero_clipped_pct == 0.0

    def test_effective_bit_depth_stored(self) -> None:
        arr = _uniform(100.0)
        assert analyze(arr, bit_depth=12).effective_bit_depth == 12
        assert analyze(arr, bit_depth=16).effective_bit_depth == 16
        assert analyze(arr, bit_depth=8).effective_bit_depth == 8

    def test_adc_max_matches_bit_depth(self) -> None:
        s = analyze(_uniform(0.0), bit_depth=12)
        assert s.adc_max == pytest.approx(4095.0)
        s16 = analyze(_uniform(0.0), bit_depth=16)
        assert s16.adc_max == pytest.approx(65535.0)

    def test_ramp_p50_near_half(self) -> None:
        arr = _ramp(bit_depth=12)
        s = analyze(arr, bit_depth=12)
        assert abs(s.p50 - 0.5) < 0.02

    def test_ramp_p99_near_one(self) -> None:
        arr = _ramp(bit_depth=12)
        s = analyze(arr, bit_depth=12)
        assert s.p99 > 0.97

    def test_percentile_ordering(self) -> None:
        arr = _ramp()
        s = analyze(arr)
        assert s.p50 <= s.p95 <= s.p99 <= s.p99_5 <= s.p99_9

    def test_black_level_near_zero_for_dark_frame(self) -> None:
        arr = _uniform(5.0)
        s = analyze(arr, bit_depth=12)
        assert s.black_level < 0.01

    def test_12bit_in_16bit_container(self) -> None:
        # Camera delivers 12-bit data packed into uint16 (values 0-4095)
        adc_max_12 = (1 << 12) - 1
        arr = _uniform(adc_max_12, dtype=np.uint16)
        # Analyse as 12-bit → should read as fully saturated
        s12 = analyze(arr, bit_depth=12)
        assert s12.saturation_pct == pytest.approx(100.0)
        # Analyse same data as 16-bit → should read as ~6% of range
        s16 = analyze(arr, bit_depth=16)
        assert s16.saturation_pct == 0.0
        assert s16.p50 < 0.1

    def test_noisy_starfield_positive_mean(self) -> None:
        rng = np.random.default_rng(42)
        arr = rng.normal(loc=500, scale=50, size=(256, 256)).clip(0).astype(np.float32)
        s = analyze(arr, bit_depth=12)
        assert s.mean_frac > 0.0
        assert s.mean_frac < 1.0

    def test_brighter_array_has_higher_mean(self) -> None:
        dim = _uniform(500.0)
        bright = _uniform(2000.0)
        assert analyze(bright, bit_depth=12).mean_frac > analyze(dim, bit_depth=12).mean_frac

    def test_partial_saturation(self) -> None:
        adc_max = (1 << 12) - 1
        arr = np.zeros((100, 100), dtype=np.float32)
        # saturate top-left 10×10 = 100 / 10000 = 1 %
        arr[:10, :10] = float(adc_max)
        s = analyze(arr, bit_depth=12)
        assert 0.9 < s.saturation_pct < 1.1

    def test_zero_clipped_partial(self) -> None:
        arr = np.ones((100, 100), dtype=np.float32) * 1000.0
        arr[:50, :] = 0.0  # 50 % of pixels are zero
        s = analyze(arr, bit_depth=12)
        assert abs(s.zero_clipped_pct - 50.0) < 0.5


# ── histogram_bins ─────────────────────────────────────────────────────────────

class TestHistogramBins:
    def test_counts_and_edges_shape(self) -> None:
        arr = _ramp()
        counts, edges = histogram_bins(arr, bit_depth=12, n_bins=512)
        assert len(counts) == 512
        assert len(edges) == 513

    def test_edges_span_zero_to_one(self) -> None:
        arr = _ramp()
        _, edges = histogram_bins(arr, bit_depth=12)
        assert edges[0] == pytest.approx(0.0)
        assert edges[-1] == pytest.approx(1.0)

    def test_counts_sum_to_total_pixels(self) -> None:
        arr = np.zeros((50, 80), dtype=np.float32)
        counts, _ = histogram_bins(arr, bit_depth=12)
        assert sum(counts) == 50 * 80

    def test_uniform_frame_concentrates_in_one_bin(self) -> None:
        arr = _uniform(2047.0)
        counts, _ = histogram_bins(arr, bit_depth=12, n_bins=512)
        nonzero = [c for c in counts if c > 0]
        assert len(nonzero) == 1

    def test_custom_n_bins(self) -> None:
        arr = _ramp()
        counts, edges = histogram_bins(arr, n_bins=128)
        assert len(counts) == 128
        assert len(edges) == 129

    def test_counts_are_integers(self) -> None:
        arr = _ramp()
        counts, _ = histogram_bins(arr)
        assert all(isinstance(c, int) for c in counts)

    def test_edges_are_floats(self) -> None:
        arr = _ramp()
        _, edges = histogram_bins(arr)
        assert all(isinstance(e, float) for e in edges)
