"""Tests for collimation frame factories — COL-130."""
from __future__ import annotations

import math

import numpy as np
import pytest

from smart_telescope.services.collimation.frame_factories import (
    donut_ring,
    focus_sequence,
    gaussian_star,
)


# ── gaussian_star ─────────────────────────────────────────────────────────────

class TestGaussianStar:
    def test_shape(self):
        f = gaussian_star(128, 256, cx=64.0, cy=64.0, fwhm_px=4.0)
        assert f.shape == (128, 256)

    def test_dtype(self):
        f = gaussian_star(64, 64, cx=32.0, cy=32.0, fwhm_px=3.0)
        assert f.dtype == np.float32

    def test_peak_at_centre(self):
        f = gaussian_star(64, 64, cx=32.0, cy=32.0, fwhm_px=4.0, peak_adu=50000.0)
        ry, rx = np.unravel_index(np.argmax(f), f.shape)
        assert abs(ry - 32) <= 1
        assert abs(rx - 32) <= 1

    def test_background_level(self):
        bg = 1000.0
        f = gaussian_star(64, 64, cx=32.0, cy=32.0, fwhm_px=4.0,
                          peak_adu=50000.0, bg_adu=bg)
        # corner pixels are far from the star → should be ≈ bg
        corner = float(f[0, 0])
        assert abs(corner - bg) < 10.0

    def test_peak_value_above_background(self):
        bg, peak = 1000.0, 40000.0
        f = gaussian_star(64, 64, cx=32.0, cy=32.0, fwhm_px=4.0,
                          peak_adu=peak, bg_adu=bg)
        assert float(np.max(f)) > bg + peak * 0.9

    def test_all_values_non_negative(self):
        f = gaussian_star(64, 64, cx=32.0, cy=32.0, fwhm_px=4.0)
        assert float(np.min(f)) >= 0.0

    def test_off_centre_star(self):
        f = gaussian_star(128, 128, cx=20.0, cy=100.0, fwhm_px=4.0, peak_adu=40000.0)
        ry, rx = np.unravel_index(np.argmax(f), f.shape)
        assert abs(rx - 20) <= 1
        assert abs(ry - 100) <= 1

    def test_narrower_star_has_sharper_peak(self):
        cx, cy = 32.0, 32.0
        f_wide   = gaussian_star(64, 64, cx, cy, fwhm_px=8.0, peak_adu=40000.0, bg_adu=0.0)
        f_narrow = gaussian_star(64, 64, cx, cy, fwhm_px=2.0, peak_adu=40000.0, bg_adu=0.0)
        # At half-max radius of narrow: ~1 px from centre, wide still bright there
        r = 1
        val_wide   = float(f_wide[int(cy), int(cx) + r])
        val_narrow = float(f_narrow[int(cy), int(cx) + r])
        assert val_narrow < val_wide


# ── donut_ring ────────────────────────────────────────────────────────────────

class TestDonutRing:
    def test_shape(self):
        f = donut_ring(256, 256, outer_cx=128.0, outer_cy=128.0,
                       outer_r=60.0, inner_r=30.0)
        assert f.shape == (256, 256)

    def test_dtype(self):
        f = donut_ring(256, 256, outer_cx=128.0, outer_cy=128.0,
                       outer_r=60.0, inner_r=30.0)
        assert f.dtype == np.float32

    def test_all_values_non_negative(self):
        f = donut_ring(256, 256, outer_cx=128.0, outer_cy=128.0,
                       outer_r=60.0, inner_r=30.0)
        assert float(np.min(f)) >= 0.0

    def test_ring_brighter_than_centre(self):
        f = donut_ring(256, 256, outer_cx=128.0, outer_cy=128.0,
                       outer_r=60.0, inner_r=30.0,
                       peak_adu=30000.0, bg_adu=1000.0)
        centre_val = float(f[128, 128])
        ring_val   = float(f[128, 128 + 60])  # pixel at outer_r from centre
        assert ring_val > centre_val

    def test_background_level_in_corners(self):
        bg = 500.0
        f = donut_ring(256, 256, outer_cx=128.0, outer_cy=128.0,
                       outer_r=40.0, inner_r=20.0, bg_adu=bg)
        corner = float(f[0, 0])
        assert abs(corner - bg) < 50.0

    def test_peak_above_background(self):
        bg, peak = 1000.0, 30000.0
        f = donut_ring(256, 256, outer_cx=128.0, outer_cy=128.0,
                       outer_r=60.0, inner_r=30.0,
                       peak_adu=peak, bg_adu=bg)
        assert float(np.max(f)) > bg + peak * 0.5

    def test_error_offsets_inner_hole(self):
        # Without error: inner hole centred at (128, 128)
        # With error: inner hole shifted
        f_no_err = donut_ring(256, 256, 128.0, 128.0, 60.0, 30.0,
                              error_x=0.0, error_y=0.0, peak_adu=30000.0, bg_adu=0.0)
        f_err    = donut_ring(256, 256, 128.0, 128.0, 60.0, 30.0,
                              error_x=20.0, error_y=0.0, peak_adu=30000.0, bg_adu=0.0)
        # The two frames should differ (inner hole position changed)
        assert not np.allclose(f_no_err, f_err)

    def test_centred_donut_has_symmetric_ring(self):
        f = donut_ring(256, 256, 128.0, 128.0, 60.0, 20.0,
                       error_x=0.0, error_y=0.0, peak_adu=30000.0, bg_adu=0.0)
        # Left ring pixel vs right ring pixel should be nearly equal
        val_left  = float(f[128, 128 - 60])
        val_right = float(f[128, 128 + 60])
        assert abs(val_left - val_right) < val_right * 0.05


# ── focus_sequence ────────────────────────────────────────────────────────────

class TestFocusSequence:
    def test_returns_list_of_correct_length(self):
        fwhms = [8.0, 6.0, 4.0, 3.0, 3.5, 5.0]
        seq = focus_sequence(128, 128, cx=64.0, cy=64.0, fwhm_values=fwhms)
        assert len(seq) == len(fwhms)

    def test_each_element_is_float32_array(self):
        seq = focus_sequence(64, 64, cx=32.0, cy=32.0,
                             fwhm_values=[4.0, 3.0, 5.0])
        for f in seq:
            assert isinstance(f, np.ndarray)
            assert f.dtype == np.float32

    def test_narrower_star_drops_faster_from_centre(self):
        seq = focus_sequence(64, 64, cx=32.0, cy=32.0,
                             fwhm_values=[8.0, 2.0], peak_adu=40000.0, bg_adu=0.0)
        # At r=4 px, wide star (fwhm=8) retains more signal than narrow (fwhm=2)
        r = 4
        wide_at_r   = float(seq[0][32, 32 + r])
        narrow_at_r = float(seq[1][32, 32 + r])
        assert wide_at_r > narrow_at_r


# ── detect_star round-trip ────────────────────────────────────────────────────

class TestDetectStarRoundTrip:
    """Verify that gaussian_star frames can be processed by detect_star."""

    def test_star_detected(self):
        from smart_telescope.domain.collimation.processing.frame import normalize_frame
        from smart_telescope.domain.collimation.processing.star_detection import detect_star
        from smart_telescope.domain.frame import FitsFrame
        from astropy.io import fits

        pixels = gaussian_star(256, 256, cx=128.0, cy=128.0,
                               fwhm_px=4.0, peak_adu=40000.0, bg_adu=500.0)
        fits_frame = FitsFrame(pixels=pixels, header=fits.Header(), exposure_seconds=1.0)
        processed  = normalize_frame(fits_frame, bit_depth=16)
        star = detect_star(processed)
        assert star is not None

    def test_detected_fwhm_is_reasonable(self):
        from smart_telescope.domain.collimation.processing.frame import normalize_frame
        from smart_telescope.domain.collimation.processing.star_detection import detect_star
        from smart_telescope.domain.frame import FitsFrame
        from astropy.io import fits

        target_fwhm = 4.0
        pixels = gaussian_star(256, 256, cx=128.0, cy=128.0,
                               fwhm_px=target_fwhm, peak_adu=40000.0, bg_adu=500.0)
        fits_frame = FitsFrame(pixels=pixels, header=fits.Header(), exposure_seconds=1.0)
        processed  = normalize_frame(fits_frame, bit_depth=16)
        star = detect_star(processed)
        assert star is not None
        # detected FWHM should be within 50 % of the generated value
        assert abs(star.fwhm_px - target_fwhm) < target_fwhm * 0.5

    def test_detected_position_is_correct(self):
        from smart_telescope.domain.collimation.processing.frame import normalize_frame
        from smart_telescope.domain.collimation.processing.star_detection import detect_star
        from smart_telescope.domain.frame import FitsFrame
        from astropy.io import fits

        cx, cy = 80.0, 160.0
        pixels = gaussian_star(256, 256, cx=cx, cy=cy,
                               fwhm_px=4.0, peak_adu=40000.0, bg_adu=500.0)
        fits_frame = FitsFrame(pixels=pixels, header=fits.Header(), exposure_seconds=1.0)
        processed  = normalize_frame(fits_frame, bit_depth=16)
        star = detect_star(processed)
        assert star is not None
        assert abs(star.center_x - cx) < 2.0
        assert abs(star.center_y - cy) < 2.0
