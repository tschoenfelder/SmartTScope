"""Unit tests for NumpyStacker — real frame stacker."""

from __future__ import annotations

import io
from typing import Any
from unittest.mock import MagicMock

import numpy as np
import pytest
from astropy.io import fits

import smart_telescope.adapters.numpy_stacker.stacker as _stacker_module
from smart_telescope.adapters.numpy_stacker.stacker import NumpyStacker
from smart_telescope.domain.frame import FitsFrame

_RNG = np.random.default_rng(42)
_H, _W = 64, 80  # small synthetic frame size

# ── astroalign mock ───────────────────────────────────────────────────────────


def _identity_register(src: np.ndarray, ref: np.ndarray) -> tuple[np.ndarray, None]:
    return src.copy(), None


@pytest.fixture(autouse=True)
def _mock_aa(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Replace module-level _aa with a MagicMock that passes frames through."""
    mock = MagicMock()
    mock.register.side_effect = _identity_register
    monkeypatch.setattr(_stacker_module, "_aa", mock)
    return mock


def _frame(
    signal: float = 1000.0,
    noise_sigma: float = 0.0,
    offset_x: int = 0,
    offset_y: int = 0,
) -> FitsFrame:
    """Return a synthetic FitsFrame with a flat signal (+noise) and optional shift."""
    pixels = np.full((_H, _W), signal, dtype=np.float32)
    if noise_sigma > 0:
        pixels += _RNG.normal(0, noise_sigma, (_H, _W)).astype(np.float32)
    # Shift by rolling (simulates small mount drift between frames)
    if offset_x or offset_y:
        pixels = np.roll(np.roll(pixels, offset_y, axis=0), offset_x, axis=1)
    return FitsFrame(pixels=pixels, header={}, exposure_seconds=2.0)


def _parse_fits_pixels(data: bytes) -> np.ndarray[Any, np.dtype[Any]]:
    with fits.open(io.BytesIO(data)) as hdul:
        return np.array(hdul[0].data, dtype=np.float32)


# ── reset ────────────────────────────────────────────────────────────────────


class TestReset:
    def test_reset_clears_frames(self, _mock_aa: MagicMock) -> None:
        s = NumpyStacker()
        s.add_frame(_frame(), 1)
        s.add_frame(_frame(), 2)
        s.reset()
        assert s.get_current_stack().frames_integrated == 0

    def test_reset_clears_rejected(self, _mock_aa: MagicMock) -> None:
        s = NumpyStacker()
        s.add_frame(_frame(), 1)
        _mock_aa.register.side_effect = Exception("no stars")
        s.add_frame(_frame(), 2)
        s.reset()
        assert s.get_current_stack().frames_rejected == 0

    def test_reset_returns_empty_data(self) -> None:
        s = NumpyStacker()
        s.add_frame(_frame(), 1)
        s.reset()
        assert s.get_current_stack().data == b""


# ── first frame (reference) ──────────────────────────────────────────────────


class TestFirstFrame:
    def test_first_frame_integrated_count_is_1(self) -> None:
        s = NumpyStacker()
        result = s.add_frame(_frame(), 1)
        assert result.frames_integrated == 1

    def test_first_frame_rejected_count_is_0(self) -> None:
        s = NumpyStacker()
        result = s.add_frame(_frame(), 1)
        assert result.frames_rejected == 0

    def test_first_frame_data_is_valid_fits(self) -> None:
        s = NumpyStacker()
        result = s.add_frame(_frame(), 1)
        assert result.data[:6] == b"SIMPLE"  # FITS magic

    def test_first_frame_pixels_preserved(self) -> None:
        s = NumpyStacker()
        f = _frame(signal=5000.0)
        result = s.add_frame(f, 1)
        pixels = _parse_fits_pixels(result.data)
        assert np.allclose(pixels, f.pixels, atol=1.0)


# ── registration (second+ frames) ────────────────────────────────────────────


class TestRegistration:
    def test_second_frame_increases_count(self) -> None:
        s = NumpyStacker()
        s.add_frame(_frame(), 1)
        result = s.add_frame(_frame(), 2)
        assert result.frames_integrated == 2

    def test_registration_failure_increments_rejected(self, _mock_aa: MagicMock) -> None:
        s = NumpyStacker()
        s.add_frame(_frame(), 1)
        _mock_aa.register.side_effect = Exception("no triangles")
        result = s.add_frame(_frame(), 2)
        assert result.frames_rejected == 1
        assert result.frames_integrated == 1

    def test_mixed_success_and_failure(self, _mock_aa: MagicMock) -> None:
        s = NumpyStacker()
        s.add_frame(_frame(), 1)
        s.add_frame(_frame(), 2)  # succeeds (identity mock)
        _mock_aa.register.side_effect = Exception("bad frame")
        result = s.add_frame(_frame(), 3)
        assert result.frames_integrated == 2
        assert result.frames_rejected == 1

    def test_astroalign_called_with_correct_arrays(self, _mock_aa: MagicMock) -> None:
        s = NumpyStacker()
        s.add_frame(_frame(signal=1000.0), 1)
        s.add_frame(_frame(signal=2000.0), 2)
        args = _mock_aa.register.call_args[0]
        assert args[0].shape == (_H, _W)
        assert args[1].shape == (_H, _W)


# ── stacking arithmetic ───────────────────────────────────────────────────────


class TestStackArithmetic:
    def test_two_identical_frames_mean_equals_signal(self) -> None:
        s = NumpyStacker()
        f = _frame(signal=3000.0)
        s.add_frame(f, 1)
        result = s.add_frame(f, 2)
        pixels = _parse_fits_pixels(result.data)
        assert np.allclose(pixels, 3000.0, atol=1.0)

    def test_mean_of_two_different_signals(self) -> None:
        s = NumpyStacker()
        s.add_frame(_frame(signal=1000.0), 1)
        result = s.add_frame(_frame(signal=3000.0), 2)
        pixels = _parse_fits_pixels(result.data)
        assert np.allclose(pixels, 2000.0, atol=1.0)

    def test_snr_improvement_with_noisy_frames(self) -> None:
        """Mean of N frames should improve SNR by sqrt(N)."""
        signal = 1000.0
        noise = 200.0
        n_frames = 16

        s = NumpyStacker()
        for i in range(1, n_frames + 1):
            s.add_frame(_frame(signal=signal, noise_sigma=noise), i)

        result = s.get_current_stack()
        assert result.frames_integrated == n_frames
        pixels = _parse_fits_pixels(result.data)
        residual = float(np.std(pixels - signal))
        expected_residual = noise / np.sqrt(n_frames)
        assert residual < expected_residual * 1.5  # 50% tolerance for RNG variance


# ── get_current_stack ─────────────────────────────────────────────────────────


class TestGetCurrentStack:
    def test_empty_stacker_returns_empty_data(self) -> None:
        s = NumpyStacker()
        result = s.get_current_stack()
        assert result.data == b""
        assert result.frames_integrated == 0
        assert result.frames_rejected == 0

    def test_matches_last_add_frame_result(self) -> None:
        s = NumpyStacker()
        last = s.add_frame(_frame(), 1)
        current = s.get_current_stack()
        assert last.frames_integrated == current.frames_integrated
        assert last.data == current.data

    def test_output_dtype_is_float32(self) -> None:
        s = NumpyStacker()
        s.add_frame(_frame(signal=5000.0), 1)
        pixels = _parse_fits_pixels(s.get_current_stack().data)
        assert pixels.dtype == np.float32
