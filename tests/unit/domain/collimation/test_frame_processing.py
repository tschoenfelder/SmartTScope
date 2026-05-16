"""Tests for collimation frame normalization — Phase 3, Task 3.1."""
from __future__ import annotations

import numpy as np
import pytest
from astropy.io import fits

from smart_telescope.domain.frame import FitsFrame
from smart_telescope.domain.collimation.processing.frame import (
    ProcessedFrame,
    normalize_frame,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _fits_frame(
    height: int = 40,
    width: int = 60,
    fill: float = 1000.0,
    dtype=np.float32,
) -> FitsFrame:
    pixels = np.full((height, width), fill, dtype=dtype)
    hdr = fits.Header()
    hdr["EXPTIME"] = 1.0
    return FitsFrame(pixels=pixels, header=hdr, exposure_seconds=1.0)


# ── normalize_frame ───────────────────────────────────────────────────────────

class TestNormalizeFrame:
    def test_output_type(self):
        f = normalize_frame(_fits_frame())
        assert isinstance(f, ProcessedFrame)

    def test_dimensions_preserved(self):
        frame = _fits_frame(height=30, width=50)
        pf = normalize_frame(frame)
        assert pf.height == 30
        assert pf.width == 50

    def test_mono_is_float32(self):
        pf = normalize_frame(_fits_frame(fill=500.0))
        assert pf.mono.dtype == np.float32

    def test_raw_is_uint16(self):
        pf = normalize_frame(_fits_frame(fill=1234.0))
        assert pf.raw.dtype == np.uint16

    def test_values_match(self):
        pf = normalize_frame(_fits_frame(fill=2048.0))
        assert np.allclose(pf.mono, 2048.0)
        assert np.all(pf.raw == 2048)

    def test_negative_pixels_clamped_in_raw(self):
        """Negative float values (e.g. after calibration) are clamped to 0 in raw."""
        frame = _fits_frame(fill=-500.0)
        pf = normalize_frame(frame)
        assert np.all(pf.raw == 0)

    def test_negative_pixels_preserved_in_mono(self):
        """mono is the original float copy — negatives preserved for algorithms."""
        frame = _fits_frame(fill=-500.0)
        pf = normalize_frame(frame)
        assert np.all(pf.mono == pytest.approx(-500.0))

    def test_overflow_clamped_to_uint16_max(self):
        frame = _fits_frame(fill=200_000.0)
        pf = normalize_frame(frame)
        assert np.all(pf.raw == 65535)

    def test_does_not_mutate_source(self):
        """normalize_frame must not alter the FitsFrame pixel buffer."""
        src = _fits_frame(fill=1000.0)
        before = src.pixels.copy()
        normalize_frame(src)
        assert np.array_equal(src.pixels, before)

    def test_mono_is_independent_copy(self):
        """Modifying ProcessedFrame.mono must not affect FitsFrame.pixels."""
        src = _fits_frame(fill=1000.0)
        pf = normalize_frame(src)
        pf.mono[0, 0] = 99999.0
        assert float(src.pixels[0, 0]) == pytest.approx(1000.0)

    def test_bit_depth_default_16(self):
        pf = normalize_frame(_fits_frame())
        assert pf.bit_depth == 16

    def test_bit_depth_custom(self):
        pf = normalize_frame(_fits_frame(), bit_depth=8)
        assert pf.bit_depth == 8

    def test_timestamp_is_positive(self):
        pf = normalize_frame(_fits_frame())
        assert pf.timestamp > 0.0

    def test_non_float32_source_converted(self):
        """uint16 source pixels are promoted to float32 in mono."""
        frame = _fits_frame(fill=300.0, dtype=np.uint16)
        pf = normalize_frame(frame)
        assert pf.mono.dtype == np.float32
        assert np.allclose(pf.mono, 300.0)


# ── ProcessedFrame.normalized ─────────────────────────────────────────────────

class TestNormalizedProperty:
    def test_range_16bit(self):
        pf = normalize_frame(_fits_frame(fill=32768.0))
        n = pf.normalized
        assert n.dtype == np.float32
        assert float(n.mean()) == pytest.approx(32768.0 / 65535.0, rel=1e-4)

    def test_full_scale_is_one(self):
        pf = normalize_frame(_fits_frame(fill=65535.0))
        assert float(pf.normalized.mean()) == pytest.approx(1.0, rel=1e-4)

    def test_zero_is_zero(self):
        pf = normalize_frame(_fits_frame(fill=0.0))
        assert float(pf.normalized.mean()) == pytest.approx(0.0, abs=1e-6)

    def test_8bit(self):
        pf = normalize_frame(_fits_frame(fill=128.0), bit_depth=8)
        assert float(pf.normalized.mean()) == pytest.approx(128.0 / 255.0, rel=1e-3)
