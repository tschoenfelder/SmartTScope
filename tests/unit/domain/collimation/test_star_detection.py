"""Tests for star detection — Phase 3, Task 3.3."""
from __future__ import annotations

import numpy as np
import pytest
from astropy.io import fits

from smart_telescope.domain.frame import FitsFrame
from smart_telescope.domain.collimation.processing.frame import normalize_frame
from smart_telescope.domain.collimation.processing.star_detection import detect_star


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_frame(
    pixels: np.ndarray,
    bit_depth: int = 16,
) -> object:
    """Wrap a numpy array as a ProcessedFrame."""
    hdr = fits.Header()
    hdr["EXPTIME"] = 1.0
    ff = FitsFrame(
        pixels=pixels.astype(np.float32),
        header=hdr,
        exposure_seconds=1.0,
    )
    return normalize_frame(ff, bit_depth=bit_depth)


def _gaussian_star(
    height: int = 200,
    width: int = 200,
    cy: float = 100.0,
    cx: float = 100.0,
    fwhm: float = 4.0,
    peak: float = 40000.0,
    bg: float = 500.0,
) -> np.ndarray:
    """Synthetic 2-D Gaussian PSF on a flat background."""
    sigma = fwhm / 2.3548
    rr, cc = np.ogrid[:height, :width]
    g = peak * np.exp(-0.5 * ((rr - cy) ** 2 + (cc - cx) ** 2) / sigma ** 2)
    return (g + bg).astype(np.float32)


# ── detect_star ───────────────────────────────────────────────────────────────

class TestDetectStar:
    def test_returns_none_on_dark_frame(self):
        data = np.full((100, 100), 500.0, dtype=np.float32)
        frame = _make_frame(data)
        assert detect_star(frame) is None

    def test_detects_gaussian_star(self):
        data = _gaussian_star()
        frame = _make_frame(data)
        result = detect_star(frame)
        assert result is not None

    def test_centroid_accuracy(self):
        """Centroid should be within 1 pixel of the true star position."""
        data = _gaussian_star(cy=105.0, cx=97.0, fwhm=4.0)
        frame = _make_frame(data)
        result = detect_star(frame)
        assert result is not None
        assert result.center_x == pytest.approx(97.0, abs=1.0)
        assert result.center_y == pytest.approx(105.0, abs=1.0)

    def test_fwhm_reasonable(self):
        data = _gaussian_star(fwhm=5.0)
        frame = _make_frame(data)
        result = detect_star(frame)
        assert result is not None
        # Expect FWHM within 50 % of the true value for a clean synthetic star
        assert result.fwhm_px == pytest.approx(5.0, rel=0.5)

    def test_snr_positive(self):
        data = _gaussian_star(peak=50000.0, bg=300.0)
        frame = _make_frame(data)
        result = detect_star(frame)
        assert result is not None
        assert result.snr > 0.0

    def test_confidence_between_0_and_1(self):
        data = _gaussian_star()
        frame = _make_frame(data)
        result = detect_star(frame)
        assert result is not None
        assert 0.0 <= result.confidence <= 1.0

    def test_rejects_single_hot_pixel(self):
        """A single hot pixel should not be reported as a star."""
        data = np.full((100, 100), 200.0, dtype=np.float32)
        data[50, 50] = 65535.0   # one pixel only
        frame = _make_frame(data)
        result = detect_star(frame)
        assert result is None

    def test_saturated_star_has_reduced_confidence(self):
        data = _gaussian_star(peak=65535.0, fwhm=4.0)
        frame = _make_frame(data)
        result_sat = detect_star(frame)

        data_normal = _gaussian_star(peak=30000.0, fwhm=4.0)
        frame_normal = _make_frame(data_normal)
        result_normal = detect_star(frame_normal)

        assert result_sat is not None
        assert result_normal is not None
        assert result_sat.confidence <= result_normal.confidence

    def test_star_at_frame_edge(self):
        """Star near the edge should still be detected (possibly with lower confidence)."""
        data = _gaussian_star(cy=5.0, cx=5.0, fwhm=3.0)
        frame = _make_frame(data)
        result = detect_star(frame)
        # May or may not detect; just ensure no crash
        # If detected, centroid should be near (5, 5)
        if result is not None:
            assert result.center_x == pytest.approx(5.0, abs=5.0)

    def test_noisy_frame_with_star(self):
        rng = np.random.default_rng(0)
        noise = rng.normal(0.0, 30.0, (200, 200)).astype(np.float32)
        star = _gaussian_star(peak=8000.0, bg=0.0)
        data = np.clip(star + noise + 300.0, 0.0, 65535.0)
        frame = _make_frame(data.astype(np.float32))
        result = detect_star(frame)
        assert result is not None
        assert result.center_x == pytest.approx(100.0, abs=3.0)
        assert result.center_y == pytest.approx(100.0, abs=3.0)

    def test_total_flux_positive(self):
        data = _gaussian_star()
        frame = _make_frame(data)
        result = detect_star(frame)
        assert result is not None
        assert result.total_flux > 0.0
