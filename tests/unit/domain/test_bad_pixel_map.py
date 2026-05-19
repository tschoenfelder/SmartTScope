"""Unit tests for bad pixel map generation."""
from __future__ import annotations

import io
import numpy as np
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from smart_telescope.domain.bad_pixel_map import (
    BpmStats,
    BpmValidationError,
    generate_bpm,
)
from smart_telescope.domain.calibration_store import CalibrationIndex
from smart_telescope.domain.camera_capabilities import CameraCapabilities, ConversionGain
from smart_telescope.domain.frame import FitsFrame


# ── helpers ───────────────────────────────────────────────────────────────────


def _make_camera(pixels: np.ndarray) -> MagicMock:
    """Return a camera mock that always returns the given pixel array."""
    from smart_telescope.ports.camera import CameraPort

    cam = MagicMock(spec=CameraPort)
    cam.get_capabilities.return_value = CameraCapabilities(
        min_gain=100, max_gain=3200,
        min_exposure_ms=0.1, max_exposure_ms=60_000,
        supports_cooling=False, supports_hcg=False, supports_lcg=True,
        supports_hdr=False, supports_black_level=False,
        bit_depth=16, pixel_size_um=3.76,
        sensor_width_px=pixels.shape[1],
        sensor_height_px=pixels.shape[0],
    )
    cam.get_gain.return_value         = 100
    cam.get_black_level.return_value  = 0
    cam.get_conversion_gain.return_value = ConversionGain.LCG
    cam.get_bit_depth.return_value    = 16
    cam.get_exposure_ms.return_value  = 0.1
    cam.get_logical_name.return_value = "TestCam"
    cam.get_serial_number.return_value = "SN001"
    cam.get_temperature.return_value  = None
    cam.capture.return_value          = FitsFrame(pixels=pixels.copy(), header={}, exposure_seconds=0.0)
    return cam


def _uniform_frame(value: int = 1000, shape: tuple = (64, 64)) -> np.ndarray:
    return np.full(shape, value, dtype=np.uint16)


# ── BpmStats ─────────────────────────────────────────────────────────────────


class TestBpmStats:
    def test_n_bad_is_sum(self) -> None:
        s = BpmStats(n_hot=10, n_dead=5, n_noisy=3, total_pixels=1000)
        assert s.n_bad == 18

    def test_bad_pct(self) -> None:
        s = BpmStats(n_hot=10, n_dead=5, n_noisy=5, total_pixels=1000)
        assert s.bad_pct == pytest.approx(2.0)

    def test_bad_pct_zero_pixels(self) -> None:
        s = BpmStats(n_hot=0, n_dead=0, n_noisy=0, total_pixels=0)
        assert s.bad_pct == 0.0

    def test_to_dict_keys(self) -> None:
        s = BpmStats(n_hot=1, n_dead=2, n_noisy=3, total_pixels=100)
        d = s.to_dict()
        assert "n_hot" in d
        assert "n_dead" in d
        assert "n_noisy" in d
        assert "n_bad" in d
        assert "bad_pct" in d


# ── generate_bpm validation ───────────────────────────────────────────────────


class TestGenerateBpmValidation:
    def test_raises_on_too_few_frames(self, tmp_path: Path) -> None:
        cam = _make_camera(_uniform_frame())
        index = CalibrationIndex(str(tmp_path))
        with pytest.raises(BpmValidationError):
            generate_bpm(cam, n_frames=3, image_root=str(tmp_path), cal_index=index)


# ── generate_bpm hot pixel detection ─────────────────────────────────────────


class TestGenerateBpmHotPixels:
    def _run(self, tmp_path: Path, base: int = 1000, hot_coords: list | None = None,
             n_frames: int = 10, hot_sigma: float = 5.0) -> tuple:
        rng = np.random.default_rng(42)
        frames = []
        for _ in range(n_frames):
            arr = rng.integers(base - 10, base + 10, size=(32, 32), dtype=np.uint16)
            if hot_coords:
                for r, c in hot_coords:
                    arr[r, c] = base + 5000  # very hot
            frames.append(arr)

        call_count = 0
        def _capture(_exp):
            nonlocal call_count
            result = FitsFrame(pixels=frames[call_count % len(frames)].copy(), header={}, exposure_seconds=0.0)
            call_count += 1
            return result

        cam = _make_camera(frames[0])
        cam.capture.side_effect = _capture

        index = CalibrationIndex(str(tmp_path))
        entry, stats = generate_bpm(
            cam, n_frames, str(tmp_path), index,
            hot_sigma=hot_sigma, dead_sigma=hot_sigma,
        )
        return entry, stats

    def test_detects_single_hot_pixel(self, tmp_path: Path) -> None:
        _, stats = self._run(tmp_path, hot_coords=[(5, 5)])
        assert stats.n_hot >= 1

    def test_no_hot_pixels_in_uniform_frame(self, tmp_path: Path) -> None:
        _, stats = self._run(tmp_path, hot_coords=None)
        assert stats.n_hot == 0

    def test_returns_calibration_entry(self, tmp_path: Path) -> None:
        entry, _ = self._run(tmp_path, hot_coords=[(3, 3)])
        assert entry.cal_type == "bpm"
        assert entry.camera_model == "TestCam"

    def test_bpm_fits_file_written(self, tmp_path: Path) -> None:
        entry, _ = self._run(tmp_path, hot_coords=[(3, 3)])
        dest = tmp_path / entry.relative_path
        assert dest.exists()
        assert dest.suffix == ".fits"

    def test_bpm_fits_has_correct_header(self, tmp_path: Path) -> None:
        from astropy.io import fits
        entry, _ = self._run(tmp_path, hot_coords=[(3, 3)])
        dest = tmp_path / entry.relative_path
        hdr = fits.getheader(str(dest))
        assert hdr["CALTYPE"] == "BPM"
        assert hdr["ISBPM"] is True

    def test_bpm_mask_marks_hot_pixel(self, tmp_path: Path) -> None:
        from astropy.io import fits
        entry, _ = self._run(tmp_path, hot_coords=[(5, 5)])
        dest = tmp_path / entry.relative_path
        mask = fits.getdata(str(dest))
        assert mask[5, 5] == 1  # hot pixel is flagged

    def test_bpm_mask_good_pixels_are_zero(self, tmp_path: Path) -> None:
        from astropy.io import fits
        entry, _ = self._run(tmp_path, hot_coords=[(5, 5)])
        dest = tmp_path / entry.relative_path
        mask = fits.getdata(str(dest))
        # Most pixels should be good
        assert mask.sum() < mask.size * 0.05  # less than 5% bad

    def test_entry_added_to_index(self, tmp_path: Path) -> None:
        index = CalibrationIndex(str(tmp_path))
        cam = _make_camera(_uniform_frame(1000, (32, 32)))
        # make n_frames uniform (no hot pixels expected, that's fine)
        generate_bpm(cam, n_frames=5, image_root=str(tmp_path), cal_index=index)
        assert len(index.entries("bpm")) == 1

    def test_progress_callback_called(self, tmp_path: Path) -> None:
        cam = _make_camera(_uniform_frame(1000, (32, 32)))
        index = CalibrationIndex(str(tmp_path))
        calls = []
        generate_bpm(cam, n_frames=5, image_root=str(tmp_path), cal_index=index,
                     progress=lambda done, total: calls.append((done, total)))
        assert len(calls) == 5
        assert calls[-1] == (5, 5)


# ── calibration_store bpm type support ───────────────────────────────────────


class TestCalibrationStoreBpm:
    def test_master_dir_bpm(self, tmp_path: Path) -> None:
        from smart_telescope.domain.calibration_store import master_dir
        d = master_dir(str(tmp_path), "TestCam", "SN001", "bpm")
        assert "bpms" in str(d)

    def test_make_entry_bpm(self, tmp_path: Path) -> None:
        from smart_telescope.domain.calibration_store import make_entry
        entry = make_entry(
            str(tmp_path), "bpm", "TestCam", "SN001",
            gain=100, offset=0, conversion_gain="LCG",
            bit_depth=16, frame_count=20,
        )
        assert entry.cal_type == "bpm"
        assert "bpm" in entry.relative_path
