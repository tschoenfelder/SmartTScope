"""Unit tests for domain/calibration_capture.py (AGT-3-1, AGT-3-2)."""
from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits

from smart_telescope.adapters.replay.camera import ReplayCamera
from smart_telescope.domain.calibration_capture import (
    BiasValidationError,
    DarkValidationError,
    prepare_bias,
    prepare_dark,
)
from smart_telescope.domain.calibration_store import CalibrationIndex


# ── helpers ───────────────────────────────────────────────────────────────────


def _write_fits(
    path: Path,
    width: int = 64,
    height: int = 48,
    value: int = 150,
    dtype: type = np.uint16,
) -> Path:
    """Write a FITS file with uniform pixel value."""
    pixels = np.full((height, width), value, dtype=dtype)
    hdu = fits.PrimaryHDU(data=pixels)
    buf = io.BytesIO()
    hdu.writeto(buf)
    path.write_bytes(buf.getvalue())
    return path


def _make_camera(tmp_path: Path, n_fits: int = 3, value: int = 150) -> ReplayCamera:
    """Create a ReplayCamera with n_fits identical bias-like FITS frames."""
    fits_paths = []
    for i in range(n_fits):
        p = tmp_path / f"frame_{i:03d}.fits"
        _write_fits(p, value=value)
        fits_paths.append(str(p))
    return ReplayCamera(fits_paths)


# ── prepare_bias — happy path ─────────────────────────────────────────────────


class TestPrepareBiasSuccess:
    def test_returns_calibration_entry(self, tmp_path: Path) -> None:
        cam = _make_camera(tmp_path)
        idx = CalibrationIndex(tmp_path)
        entry = prepare_bias(cam, 3, tmp_path, idx)
        assert entry.cal_type == "bias"

    def test_master_fits_file_is_created(self, tmp_path: Path) -> None:
        cam = _make_camera(tmp_path)
        idx = CalibrationIndex(tmp_path)
        entry = prepare_bias(cam, 3, tmp_path, idx)
        dest = tmp_path / entry.relative_path
        assert dest.exists()

    def test_entry_added_to_index(self, tmp_path: Path) -> None:
        cam = _make_camera(tmp_path)
        idx = CalibrationIndex(tmp_path)
        entry = prepare_bias(cam, 3, tmp_path, idx)
        assert len(idx.entries("bias")) == 1
        assert idx.entries("bias")[0].relative_path == entry.relative_path

    def test_frame_count_in_entry(self, tmp_path: Path) -> None:
        cam = _make_camera(tmp_path, n_fits=5)
        idx = CalibrationIndex(tmp_path)
        entry = prepare_bias(cam, 5, tmp_path, idx)
        assert entry.frame_count == 5

    def test_gain_recorded_in_entry(self, tmp_path: Path) -> None:
        cam = _make_camera(tmp_path)
        cam.set_gain(200)
        idx = CalibrationIndex(tmp_path)
        entry = prepare_bias(cam, 3, tmp_path, idx)
        assert entry.gain == 200

    def test_gain_param_overrides_camera(self, tmp_path: Path) -> None:
        cam = _make_camera(tmp_path)
        idx = CalibrationIndex(tmp_path)
        entry = prepare_bias(cam, 3, tmp_path, idx, gain=500)
        assert entry.gain == 500

    def test_offset_param_applied(self, tmp_path: Path) -> None:
        cam = _make_camera(tmp_path)
        idx = CalibrationIndex(tmp_path)
        entry = prepare_bias(cam, 3, tmp_path, idx, offset=10)
        assert entry.offset == 10

    def test_master_fits_has_caltype_header(self, tmp_path: Path) -> None:
        cam = _make_camera(tmp_path)
        idx = CalibrationIndex(tmp_path)
        entry = prepare_bias(cam, 3, tmp_path, idx)
        dest = tmp_path / entry.relative_path
        with fits.open(str(dest)) as hdul:
            assert hdul[0].header.get("CALTYPE") == "BIAS"

    def test_master_fits_has_nframes_header(self, tmp_path: Path) -> None:
        cam = _make_camera(tmp_path, n_fits=4)
        idx = CalibrationIndex(tmp_path)
        entry = prepare_bias(cam, 4, tmp_path, idx)
        dest = tmp_path / entry.relative_path
        with fits.open(str(dest)) as hdul:
            assert hdul[0].header.get("NFRAMES") == 4

    def test_master_pixels_are_mean_of_frames(self, tmp_path: Path) -> None:
        """Two frames with values 100 and 200 → mean 150."""
        p1 = tmp_path / "a.fits"
        p2 = tmp_path / "b.fits"
        _write_fits(p1, value=100)
        _write_fits(p2, value=200)
        cam = ReplayCamera([str(p1), str(p2)])
        idx = CalibrationIndex(tmp_path)
        entry = prepare_bias(cam, 2, tmp_path, idx)
        dest = tmp_path / entry.relative_path
        with fits.open(str(dest)) as hdul:
            mean_val = float(np.mean(hdul[0].data))
        assert abs(mean_val - 150.0) < 0.5

    def test_progress_callback_called(self, tmp_path: Path) -> None:
        cam = _make_camera(tmp_path, n_fits=4)
        idx = CalibrationIndex(tmp_path)
        calls: list[tuple[int, int]] = []
        prepare_bias(cam, 4, tmp_path, idx, progress=lambda d, t: calls.append((d, t)))
        assert len(calls) == 4
        assert calls[-1] == (4, 4)

    def test_index_persists_after_save(self, tmp_path: Path) -> None:
        cam = _make_camera(tmp_path)
        idx = CalibrationIndex(tmp_path)
        entry = prepare_bias(cam, 3, tmp_path, idx)
        idx.save()
        reloaded = CalibrationIndex.load(tmp_path)
        assert len(reloaded.entries("bias")) == 1
        assert reloaded.entries("bias")[0].relative_path == entry.relative_path


# ── prepare_bias — validation failures ───────────────────────────────────────


class TestPrepareBiasValidation:
    def test_raises_when_all_pixels_zero(self, tmp_path: Path) -> None:
        cam = _make_camera(tmp_path, value=0)
        idx = CalibrationIndex(tmp_path)
        with pytest.raises(BiasValidationError, match="p0.1"):
            prepare_bias(cam, 3, tmp_path, idx)

    def test_no_master_file_created_on_validation_failure(self, tmp_path: Path) -> None:
        cam = _make_camera(tmp_path, value=0)
        idx = CalibrationIndex(tmp_path)
        with pytest.raises(BiasValidationError):
            prepare_bias(cam, 3, tmp_path, idx)
        assert len(idx.entries("bias")) == 0

    def test_raises_on_invalid_n_frames(self, tmp_path: Path) -> None:
        cam = _make_camera(tmp_path)
        idx = CalibrationIndex(tmp_path)
        with pytest.raises(ValueError):
            prepare_bias(cam, 0, tmp_path, idx)


# ── prepare_dark — happy path ─────────────────────────────────────────────────


class TestPrepareDarkSuccess:
    def test_returns_entry_and_none_warning(self, tmp_path: Path) -> None:
        cam = _make_camera(tmp_path, value=150)
        idx = CalibrationIndex(tmp_path)
        entry, warn = prepare_dark(cam, 2000.0, 3, tmp_path, idx)
        assert entry.cal_type == "dark"
        assert warn is None

    def test_master_fits_file_created(self, tmp_path: Path) -> None:
        cam = _make_camera(tmp_path)
        idx = CalibrationIndex(tmp_path)
        entry, _ = prepare_dark(cam, 2000.0, 3, tmp_path, idx)
        assert (tmp_path / entry.relative_path).exists()

    def test_entry_added_to_index(self, tmp_path: Path) -> None:
        cam = _make_camera(tmp_path)
        idx = CalibrationIndex(tmp_path)
        entry, _ = prepare_dark(cam, 2000.0, 3, tmp_path, idx)
        assert len(idx.entries("dark")) == 1
        assert idx.entries("dark")[0].relative_path == entry.relative_path

    def test_exposure_ms_recorded_in_entry(self, tmp_path: Path) -> None:
        cam = _make_camera(tmp_path)
        idx = CalibrationIndex(tmp_path)
        entry, _ = prepare_dark(cam, 5000.0, 3, tmp_path, idx)
        assert entry.exposure_ms == pytest.approx(5000.0, abs=1.0)

    def test_gain_param_applied(self, tmp_path: Path) -> None:
        cam = _make_camera(tmp_path)
        idx = CalibrationIndex(tmp_path)
        entry, _ = prepare_dark(cam, 2000.0, 3, tmp_path, idx, gain=400)
        assert entry.gain == 400

    def test_master_fits_has_caltype_dark(self, tmp_path: Path) -> None:
        cam = _make_camera(tmp_path)
        idx = CalibrationIndex(tmp_path)
        entry, _ = prepare_dark(cam, 2000.0, 3, tmp_path, idx)
        dest = tmp_path / entry.relative_path
        with fits.open(str(dest)) as hdul:
            assert hdul[0].header.get("CALTYPE") == "DARK"

    def test_progress_callback_called(self, tmp_path: Path) -> None:
        cam = _make_camera(tmp_path, n_fits=4)
        idx = CalibrationIndex(tmp_path)
        calls: list[tuple[int, int]] = []
        prepare_dark(cam, 2000.0, 4, tmp_path, idx, progress=lambda d, t: calls.append((d, t)))
        assert len(calls) == 4
        assert calls[-1] == (4, 4)

    def test_index_persists_after_save(self, tmp_path: Path) -> None:
        cam = _make_camera(tmp_path)
        idx = CalibrationIndex(tmp_path)
        entry, _ = prepare_dark(cam, 2000.0, 3, tmp_path, idx)
        idx.save()
        reloaded = CalibrationIndex.load(tmp_path)
        assert len(reloaded.entries("dark")) == 1
        assert reloaded.entries("dark")[0].relative_path == entry.relative_path


# ── prepare_dark — validation failures ───────────────────────────────────────


class TestPrepareDarkValidation:
    def test_raises_when_pixels_zero(self, tmp_path: Path) -> None:
        cam = _make_camera(tmp_path, value=0)
        idx = CalibrationIndex(tmp_path)
        with pytest.raises(DarkValidationError):
            prepare_dark(cam, 2000.0, 3, tmp_path, idx)

    def test_raises_when_saturated(self, tmp_path: Path) -> None:
        """Saturated dark (all pixels at max) must fail validation."""
        cam = _make_camera(tmp_path, value=65535)
        idx = CalibrationIndex(tmp_path)
        with pytest.raises(DarkValidationError, match="saturated"):
            prepare_dark(cam, 2000.0, 3, tmp_path, idx)

    def test_no_entry_on_validation_failure(self, tmp_path: Path) -> None:
        cam = _make_camera(tmp_path, value=0)
        idx = CalibrationIndex(tmp_path)
        with pytest.raises(DarkValidationError):
            prepare_dark(cam, 2000.0, 3, tmp_path, idx)
        assert len(idx.entries("dark")) == 0

    def test_raises_on_invalid_n_frames(self, tmp_path: Path) -> None:
        cam = _make_camera(tmp_path)
        idx = CalibrationIndex(tmp_path)
        with pytest.raises(ValueError):
            prepare_dark(cam, 2000.0, 0, tmp_path, idx)

    def test_raises_on_zero_exposure(self, tmp_path: Path) -> None:
        cam = _make_camera(tmp_path)
        idx = CalibrationIndex(tmp_path)
        with pytest.raises(ValueError):
            prepare_dark(cam, 0.0, 3, tmp_path, idx)
