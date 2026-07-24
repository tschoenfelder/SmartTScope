"""Unit tests for focus sharpness metrics."""
import numpy as np
import pytest

from smart_telescope.domain.focus_metric import half_flux_diameter, laplacian_variance, multi_star_hfd


def _gaussian_frame(sigma: float, size: int = 64) -> np.ndarray:
    cy, cx = size / 2.0, size / 2.0
    y, x = np.mgrid[:size, :size].astype(np.float64)
    return (10000.0 * np.exp(-((x - cx) ** 2 + (y - cy) ** 2) / (2.0 * sigma ** 2))).astype(np.float32)


def _multi_star_frame(
    sigma: float, background: float = 50.0, size: int = 600,
    centers: list[tuple[int, int]] | None = None,
    amplitudes: list[float] | None = None,
) -> np.ndarray:
    centers = centers or [(80, 80), (80, 420), (300, 250), (500, 100), (500, 420)]
    amplitudes = amplitudes or [6000.0, 9000.0, 4000.0, 8000.0, 5000.0]
    y, x = np.mgrid[:size, :size].astype(np.float64)
    pixels = np.full((size, size), background, dtype=np.float64)
    for (cy, cx), amp in zip(centers, amplitudes):
        pixels += amp * np.exp(-((x - cx) ** 2 + (y - cy) ** 2) / (2.0 * sigma ** 2))
    return pixels.astype(np.float32)


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


class TestMultiStarHfd:
    def test_isolates_true_star_size_unlike_whole_frame_hfd(self) -> None:
        """M10-051: on a frame with several stars scattered across it, the
        whole-frame half_flux_diameter() is dominated by the spread between
        stars (huge, near the frame's own half-diagonal) rather than any
        star's actual blur. multi_star_hfd() must stay close to the true
        per-star HFD instead."""
        frame = _multi_star_frame(sigma=3.0)
        single_star_hfd = half_flux_diameter(_gaussian_frame(3.0, size=200))
        whole_frame_hfd = half_flux_diameter(frame)
        multi_hfd = multi_star_hfd(frame)

        assert whole_frame_hfd > 50 * multi_hfd  # whole-frame is wildly inflated
        assert multi_hfd == pytest.approx(single_star_hfd, rel=0.2)

    def test_tight_stars_smaller_than_wide_stars(self) -> None:
        tight = multi_star_hfd(_multi_star_frame(sigma=2.0))
        wide  = multi_star_hfd(_multi_star_frame(sigma=8.0))
        assert tight < wide

    def test_robust_to_background_drift_between_frames(self) -> None:
        """A background level shift alone (no change in star sharpness)
        must not move the metric appreciably — this is what let the
        pre-fix whole-frame metric track sky-darkening instead of focus."""
        low_bg  = multi_star_hfd(_multi_star_frame(sigma=4.0, background=20.0))
        high_bg = multi_star_hfd(_multi_star_frame(sigma=4.0, background=200.0))
        assert low_bg == pytest.approx(high_bg, rel=0.05)

    def test_returns_none_when_no_star_detected(self) -> None:
        # Uniform, no signal — no candidate blob passes the star-shape checks,
        # so the caller must be told "no reliable star" rather than get a
        # number back (a whole-frame fallback would be actively misleading —
        # see M10-051: this is exactly what let a whole-frame HFD silently
        # track sky-brightness drift and hot pixels instead of real focus).
        arr = np.ones((32, 32), dtype=np.float32) * 100.0
        assert multi_star_hfd(arr) is None

    def test_rejects_oversized_blob(self) -> None:
        # A blob covering nearly the whole frame (e.g. a bloomed satellite
        # trail or nebula) is not star-like and should be rejected, not
        # measured — this frame has no other candidate, so the result must
        # be None rather than a number.
        arr = np.full((64, 64), 50.0, dtype=np.float32)
        arr[4:60, 4:60] = 5000.0  # covers ~78% of the frame, filling the ROI edge-to-edge
        assert multi_star_hfd(arr) is None

    def test_raises_on_1d_array(self) -> None:
        with pytest.raises(ValueError, match="2-D"):
            multi_star_hfd(np.ones(10))


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
