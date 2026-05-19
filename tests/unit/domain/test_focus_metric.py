"""Unit tests for focus sharpness metrics."""
import numpy as np
import pytest

from smart_telescope.domain.focus_metric import half_flux_diameter, laplacian_variance


def _gaussian_frame(sigma: float, size: int = 64) -> np.ndarray:
    cy, cx = size / 2.0, size / 2.0
    y, x = np.mgrid[:size, :size].astype(np.float64)
    return (10000.0 * np.exp(-((x - cx) ** 2 + (y - cy) ** 2) / (2.0 * sigma ** 2))).astype(np.float32)


class TestHalfFluxDiameter:
    def test_tight_star_smaller_than_wide_star(self) -> None:
        assert half_flux_diameter(_gaussian_frame(2.0)) < half_flux_diameter(_gaussian_frame(8.0))

    def test_returns_float(self) -> None:
        assert isinstance(half_flux_diameter(_gaussian_frame(3.0)), float)

    def test_no_signal_returns_large_value(self) -> None:
        arr = np.ones((32, 32), dtype=np.float32) * 100.0  # uniform → background = signal → 0 after subtract
        result = half_flux_diameter(arr)
        assert result == float(max(arr.shape))

    def test_decreases_monotonically_toward_focus(self) -> None:
        sigmas = [10.0, 6.0, 3.0, 6.0, 10.0]
        hfds = [half_flux_diameter(_gaussian_frame(s)) for s in sigmas]
        # Tightest star (index 2) must have the smallest HFD
        assert hfds[2] == min(hfds)

    def test_raises_on_1d_array(self) -> None:
        with pytest.raises(ValueError, match="2-D"):
            half_flux_diameter(np.ones(10))

    def test_raises_on_too_small_array(self) -> None:
        with pytest.raises(ValueError, match="too small"):
            half_flux_diameter(np.ones((2, 5)))


class TestLaplacianVariance:
    def test_uniform_array_returns_zero(self) -> None:
        arr = np.ones((10, 10), dtype=np.float32) * 128
        assert laplacian_variance(arr) == 0.0

    def test_sharp_edges_return_higher_value_than_blurred(self) -> None:
        rng = np.random.default_rng(42)
        sharp = rng.integers(0, 65535, size=(64, 64)).astype(np.float32)
        # Manual box blur via cumulative sum (no scipy required)
        k = 5
        cs = np.cumsum(np.cumsum(sharp, axis=0), axis=1)
        blurred = (
            cs[k:, k:] - cs[:-k, k:] - cs[k:, :-k] + cs[:-k, :-k]
        ).astype(np.float32) / (k * k)
        assert laplacian_variance(sharp[k:, k:]) > laplacian_variance(blurred)

    def test_impulse_produces_nonzero_metric(self) -> None:
        arr = np.zeros((10, 10), dtype=np.float32)
        arr[5, 5] = 1000.0
        assert laplacian_variance(arr) > 0.0

    def test_raises_on_1d_array(self) -> None:
        with pytest.raises(ValueError, match="2-D"):
            laplacian_variance(np.ones(10))

    def test_raises_on_too_small_array(self) -> None:
        with pytest.raises(ValueError, match="too small"):
            laplacian_variance(np.ones((2, 5)))

    def test_returns_float(self) -> None:
        arr = np.arange(25, dtype=np.float32).reshape(5, 5)
        assert isinstance(laplacian_variance(arr), float)

    def test_symmetric_result_for_transposed_input(self) -> None:
        rng = np.random.default_rng(7)
        arr = rng.random((20, 30)).astype(np.float32)
        assert laplacian_variance(arr) == pytest.approx(laplacian_variance(arr.T), rel=1e-5)
