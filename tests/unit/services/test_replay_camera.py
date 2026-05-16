"""Tests for ReplayCameraAdapter — COL-130."""
from __future__ import annotations

import numpy as np
import pytest

from smart_telescope.adapters.replay.camera import ReplayCameraAdapter
from smart_telescope.domain.frame import FitsFrame
from smart_telescope.ports.camera import CaptureAbortedError


# ── Helpers ───────────────────────────────────────────────────────────────────

def _frame(fill: float, h: int = 32, w: int = 32) -> np.ndarray:
    return np.full((h, w), fill, dtype=np.float32)


def _camera(n_frames: int = 3, cycle: bool = True) -> ReplayCameraAdapter:
    frames = [_frame(float(i + 1) * 1000.0) for i in range(n_frames)]
    return ReplayCameraAdapter(frames, bit_depth=16, cycle=cycle)


# ── Construction ──────────────────────────────────────────────────────────────

class TestConstruction:
    def test_empty_frames_raises(self):
        with pytest.raises(ValueError):
            ReplayCameraAdapter([])

    def test_connect_returns_true(self):
        cam = _camera()
        assert cam.connect() is True

    def test_bit_depth_preserved(self):
        cam = ReplayCameraAdapter([_frame(1.0)], bit_depth=12)
        assert cam.get_bit_depth() == 12


# ── Frame serving ─────────────────────────────────────────────────────────────

class TestFrameServing:
    def test_capture_returns_fits_frame(self):
        cam = _camera()
        f = cam.capture(1.0)
        assert isinstance(f, FitsFrame)

    def test_first_frame_pixels_match(self):
        arr = np.full((32, 32), 5000.0, dtype=np.float32)
        cam = ReplayCameraAdapter([arr])
        f = cam.capture(1.0)
        assert np.allclose(f.pixels, arr)

    def test_frames_served_in_order(self):
        frames = [_frame(1000.0), _frame(2000.0), _frame(3000.0)]
        cam = ReplayCameraAdapter(frames, cycle=False)
        vals = [float(cam.capture(1.0).pixels[0, 0]) for _ in range(3)]
        assert vals == [1000.0, 2000.0, 3000.0]

    def test_frame_index_increments(self):
        cam = _camera(3)
        assert cam.frame_index == 0
        cam.capture(1.0)
        assert cam.frame_index == 1
        cam.capture(1.0)
        assert cam.frame_index == 2

    def test_exposure_seconds_stored_in_frame(self):
        cam = _camera()
        f = cam.capture(2.5)
        assert f.exposure_seconds == pytest.approx(2.5)


# ── Cycling ───────────────────────────────────────────────────────────────────

class TestCycling:
    def test_cycles_when_flag_true(self):
        frames = [_frame(1000.0), _frame(2000.0)]
        cam = ReplayCameraAdapter(frames, cycle=True)
        # exhaust sequence, then wrap
        cam.capture(1.0); cam.capture(1.0)
        f = cam.capture(1.0)
        assert float(f.pixels[0, 0]) == pytest.approx(1000.0)

    def test_raises_when_exhausted_and_no_cycle(self):
        cam = ReplayCameraAdapter([_frame(1.0)], cycle=False)
        cam.capture(1.0)
        with pytest.raises(CaptureAbortedError):
            cam.capture(1.0)

    def test_reset_rewinds_to_start(self):
        frames = [_frame(1000.0), _frame(2000.0)]
        cam = ReplayCameraAdapter(frames, cycle=False)
        cam.capture(1.0); cam.capture(1.0)
        cam.reset()
        f = cam.capture(1.0)
        assert float(f.pixels[0, 0]) == pytest.approx(1000.0)


# ── Settings ──────────────────────────────────────────────────────────────────

class TestSettings:
    def test_exposure_set_and_get(self):
        cam = _camera()
        cam.set_exposure_ms(500.0)
        assert cam.get_exposure_ms() == pytest.approx(500.0)

    def test_gain_set_and_get(self):
        cam = _camera()
        cam.set_gain(200)
        assert cam.get_gain() == 200

    def test_logical_name(self):
        cam = _camera()
        assert cam.get_logical_name() == "replay_array"

    def test_serial_number_is_string(self):
        cam = _camera()
        assert isinstance(cam.get_serial_number(), str)

    def test_temperature_is_none(self):
        cam = _camera()
        assert cam.get_temperature() is None
