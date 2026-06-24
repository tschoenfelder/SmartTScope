"""Tests for ServiceFrame common input dataclass (M7-005 / IF-001)."""

from __future__ import annotations

import numpy as np
import pytest

from smart_telescope.domain.frame import FitsFrame
from smart_telescope.domain.service_frame import FrameValidationError, ServiceFrame


def _pixels() -> np.ndarray:
    return np.zeros((128, 128), dtype=np.float32)


def _minimal(**overrides) -> ServiceFrame:
    kwargs = dict(
        frame_id="f1",
        camera_id="cam0",
        optical_train_id="c8_native",
        pixel_data=_pixels(),
        bit_depth=16,
        timestamp="2026-01-01T00:00:00+00:00",
        exposure_s=2.0,
        gain=100,
        binning_x=1,
        binning_y=1,
        sensor_width_px=128,
        sensor_height_px=128,
    )
    kwargs.update(overrides)
    return ServiceFrame(**kwargs)


# ── TEST: valid frame passes validation ───────────────────────────────────────

def test_valid_frame_passes_validation():
    sf = _minimal()
    sf.validate()   # must not raise


# ── TEST: missing mandatory field raises ──────────────────────────────────────

def test_missing_frame_id_raises():
    with pytest.raises(TypeError):
        ServiceFrame(
            camera_id="cam0",
            optical_train_id="c8",
            pixel_data=_pixels(),
            bit_depth=16,
            timestamp="2026-01-01T00:00:00+00:00",
            exposure_s=1.0,
            gain=100,
            binning_x=1,
            binning_y=1,
            sensor_width_px=128,
            sensor_height_px=128,
        )   # type: ignore[call-arg]  — frame_id missing


# ── TEST: optional fields default to None ─────────────────────────────────────

def test_optional_fields_default_none():
    sf = _minimal()
    assert sf.is_mono_or_bayer is None
    assert sf.ra is None
    assert sf.dec is None
    assert sf.tracking_on is None
    assert sf.pixel_size_um is None


# ── TEST: pixel_data not mutated ──────────────────────────────────────────────

def test_pixel_data_not_modified():
    px = _pixels()
    original_sum = float(px.sum())
    sf = _minimal(pixel_data=px)
    sf.validate()
    assert float(sf.pixel_data.sum()) == original_sum


# ── TEST: from_fits_frame factory ─────────────────────────────────────────────

def test_from_fits_frame_factory():
    pixels = np.ones((64, 64), dtype=np.float32) * 1000.0
    fits_frame = FitsFrame(pixels=pixels, header={}, exposure_seconds=3.0)
    sf = ServiceFrame.from_fits_frame(
        fits_frame,
        frame_id="f42",
        camera_id="main",
        optical_train_id="c8_native",
        gain=200,
    )
    sf.validate()
    assert sf.frame_id == "f42"
    assert sf.exposure_s == 3.0
    assert sf.gain == 200
    assert sf.sensor_width_px == 64
    assert sf.sensor_height_px == 64
