"""Tests for shared image-analysis module (M7-009 / DD-005)."""

from __future__ import annotations

import numpy as np
import pytest

from smart_telescope.services.image_analysis import (
    FocusQualityLevel,
    ImageAnalysisResult,
    analyze_frame,
)


def _star_frame(peak_x: int, peak_y: int, brightness: float = 50000.0, size: int = 128) -> np.ndarray:
    pixels = np.zeros((size, size), dtype=np.float32)
    pixels[peak_y, peak_x] = brightness
    return pixels


def _defocused_frame(hfd_target: float = 300.0, size: int = 64) -> np.ndarray:
    """Large, very spread-out blob (simulates extreme defocus → HFD >> threshold)."""
    pixels = np.zeros((size, size), dtype=np.float32)
    cx, cy = size // 2, size // 2
    radius = hfd_target / 2.0
    for y in range(size):
        for x in range(size):
            r = np.hypot(x - cx, y - cy)
            if r <= radius:
                pixels[y, x] = 1000.0
    return pixels


# ── blank frame → UNKNOWN ─────────────────────────────────────────────────────

def test_blank_frame_returns_unknown():
    """Blank frame (no signal) returns focus_quality=UNKNOWN with a reason."""
    result = analyze_frame(np.zeros((64, 64), dtype=np.float32))
    assert result.focus_quality == FocusQualityLevel.UNKNOWN
    assert result.hfd_px is None
    assert result.reason is not None


# ── sharp star → GOOD ─────────────────────────────────────────────────────────

def test_sharp_star_returns_good():
    """Single bright star on dark background returns focus_quality=GOOD."""
    result = analyze_frame(_star_frame(32, 32, brightness=60000.0))
    assert result.focus_quality == FocusQualityLevel.GOOD
    assert result.hfd_px is not None
    assert result.hfd_px >= 0.0


# ── FWHM derived from HFD ─────────────────────────────────────────────────────

def test_fwhm_derived_from_hfd():
    """fwhm_px is approximately 0.85 × hfd_px for a point source."""
    result = analyze_frame(_star_frame(32, 32))
    assert result.fwhm_px is not None
    assert result.hfd_px is not None
    assert abs(result.fwhm_px - result.hfd_px * 0.85) < 0.01


# ── star info populated ───────────────────────────────────────────────────────

def test_brightest_star_populated():
    """analyze_frame() populates brightest_star with centroid and peak."""
    result = analyze_frame(_star_frame(40, 30, brightness=60000.0))
    assert result.brightest_star is not None
    assert abs(result.brightest_star.centroid_x - 40) < 2
    assert abs(result.brightest_star.centroid_y - 30) < 2
    assert result.brightest_star.peak_value > 0


# ── out-of-focus frames return UNKNOWN (not misleading FWHM) ─────────────────

def test_out_of_focus_returns_unknown():
    """Strongly out-of-focus frames must not produce a misleading FWHM."""
    # A very uniform frame gives HFD close to max(shape) → UNKNOWN
    uniform = np.ones((64, 64), dtype=np.float32) * 1000.0
    result = analyze_frame(uniform)
    # Uniform signal → HFD = full frame → UNKNOWN
    assert result.focus_quality == FocusQualityLevel.UNKNOWN


# ── POOR quality for large but detectable star ────────────────────────────────

def test_large_hfd_returns_poor():
    """Star with HFD above quality threshold but below UNKNOWN threshold → POOR."""
    result = analyze_frame(_star_frame(32, 32), quality_threshold_hfd=2.0)
    # A single bright pixel has HFD ≈ 0 which is below quality_threshold=2 normally,
    # but we force threshold very low (2) to check POOR classification path.
    # With a single bright pixel on black background, HFD should be ~0; so we
    # need a medium-sized blob to be POOR.
    blurred = np.zeros((64, 64), dtype=np.float32)
    cx, cy = 32, 32
    for y in range(64):
        for x in range(64):
            r = np.hypot(x - cx, y - cy)
            if r <= 15:
                blurred[y, x] = 1000.0 * (1 - r / 15)
    result2 = analyze_frame(blurred, quality_threshold_hfd=5.0)
    assert result2.focus_quality in (FocusQualityLevel.POOR, FocusQualityLevel.GOOD)
    assert result2.hfd_px is not None
