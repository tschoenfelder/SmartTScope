"""Unit tests for laplacian_variance focus sharpness metric."""
import numpy as np
import pytest

from smart_telescope.domain.focus_metric import laplacian_variance


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
