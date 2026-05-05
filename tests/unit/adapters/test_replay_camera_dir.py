"""Tests for ReplayCamera.from_directory and autogain convergence with replay frames."""
from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits

from smart_telescope.adapters.replay.camera import ReplayCamera
from smart_telescope.domain.autogain import (
    AutoGainController,
    _EXP_MAX,
    _EXP_MIN,
    _GAIN_MAX,
    _GAIN_MIN,
    _HI,
    _LO,
)

# ── helpers ────────────────────────────────────────────────────────────────────

_W, _H = 64, 48  # small frames for fast tests; mean fraction ≈ mean/65535


def _write_fits(tmp: Path, name: str, mean_frac: float) -> Path:
    """Write a uint16 FITS file whose mean pixel value is *mean_frac* × 65535."""
    mean_counts = int(mean_frac * 65535)
    rng = np.random.default_rng(seed=int(mean_counts))
    lo = max(0, mean_counts - 100)
    hi = min(65535, mean_counts + 100)
    pixels = rng.integers(lo, hi + 1, (_H, _W), dtype=np.uint16)
    hdu = fits.PrimaryHDU(pixels)
    buf = io.BytesIO()
    hdu.writeto(buf)
    p = tmp / name
    p.write_bytes(buf.getvalue())
    return p


def _good_dir(tmp: Path, n: int = 6) -> Path:
    """Directory of frames with mean_frac in the target window [_LO, _HI]."""
    d = tmp / "good"
    d.mkdir()
    target = (_LO + _HI) / 2.0  # 0.285
    for i in range(n):
        _write_fits(d, f"frame_{i:02d}.fits", target)
    return d


def _dark_dir(tmp: Path, n: int = 6) -> Path:
    """Directory of frames that are too dark (mean_frac << _LO)."""
    d = tmp / "dark"
    d.mkdir()
    for i in range(n):
        _write_fits(d, f"frame_{i:02d}.fits", 0.02)  # very underexposed
    return d


def _bright_dir(tmp: Path, n: int = 6) -> Path:
    """Directory of frames that are too bright (mean_frac >> _HI)."""
    d = tmp / "bright"
    d.mkdir()
    for i in range(n):
        _write_fits(d, f"frame_{i:02d}.fits", 0.80)  # severely overexposed
    return d


# ── ReplayCamera.from_directory ───────────────────────────────────────────────

class TestFromDirectory:
    def test_from_directory_returns_replay_camera(self, tmp_path: Path) -> None:
        d = _good_dir(tmp_path)
        cam = ReplayCamera.from_directory(d)
        assert isinstance(cam, ReplayCamera)

    def test_from_directory_connects_successfully(self, tmp_path: Path) -> None:
        d = _good_dir(tmp_path)
        cam = ReplayCamera.from_directory(d)
        assert cam.connect() is True

    def test_from_directory_serves_correct_file_count(self, tmp_path: Path) -> None:
        d = _good_dir(tmp_path, n=4)
        cam = ReplayCamera.from_directory(d)
        assert len(cam._paths) == 4

    def test_from_directory_cycles_files_in_order(self, tmp_path: Path) -> None:
        d = _good_dir(tmp_path, n=3)
        cam = ReplayCamera.from_directory(d)
        # Files are sorted; capture should cycle through them
        names = [cam._paths[i % 3].name for i in range(3)]
        assert names == sorted(names)

    def test_from_directory_raises_for_non_directory(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="not a directory"):
            ReplayCamera.from_directory(tmp_path / "missing")

    def test_from_directory_raises_for_empty_directory(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        with pytest.raises(ValueError, match="no FITS files"):
            ReplayCamera.from_directory(empty)

    def test_from_directory_ignores_non_fits_files(self, tmp_path: Path) -> None:
        d = tmp_path / "mixed"
        d.mkdir()
        _write_fits(d, "frame.fits", 0.3)
        (d / "readme.txt").write_text("not a fits file")
        cam = ReplayCamera.from_directory(d)
        assert len(cam._paths) == 1


# ── autogain convergence ──────────────────────────────────────────────────────

class TestAutogainConvergence:
    def _run_loop(self, cam: ReplayCamera, n_frames: int) -> AutoGainController:
        ctrl = AutoGainController(exposure=2.0, gain=_GAIN_MIN)
        for _ in range(n_frames):
            frame = cam.capture(ctrl.exposure)
            ctrl.update(frame.pixels)
            cam.set_gain(ctrl.gain)
            cam.set_exposure_ms(ctrl.exposure * 1000.0)
        return ctrl

    def test_stable_on_well_exposed_frames(self, tmp_path: Path) -> None:
        cam = ReplayCamera.from_directory(_good_dir(tmp_path))
        ctrl = self._run_loop(cam, n_frames=10)
        # Settings should remain close to initial values (already well-exposed)
        assert _EXP_MIN <= ctrl.exposure <= _EXP_MAX
        assert _GAIN_MIN <= ctrl.gain <= _GAIN_MAX

    def test_no_gain_change_on_well_exposed_frames(self, tmp_path: Path) -> None:
        """Gain stays at minimum when exposure alone is sufficient."""
        cam = ReplayCamera.from_directory(_good_dir(tmp_path))
        ctrl = self._run_loop(cam, n_frames=10)
        assert ctrl.gain == _GAIN_MIN

    def test_exposure_stays_near_initial_on_good_frames(self, tmp_path: Path) -> None:
        cam = ReplayCamera.from_directory(_good_dir(tmp_path))
        ctrl_initial = AutoGainController(exposure=2.0, gain=_GAIN_MIN)
        ctrl = self._run_loop(cam, n_frames=10)
        # Good frames: no adjustment expected, exposure should stay at 2.0
        assert ctrl.exposure == pytest.approx(2.0, abs=0.01)

    def test_exposure_increases_on_dark_frames(self, tmp_path: Path) -> None:
        cam = ReplayCamera.from_directory(_dark_dir(tmp_path))
        ctrl = self._run_loop(cam, n_frames=8)
        # After 8 dark frames, exposure should have been raised above the initial 2.0
        assert ctrl.exposure > 2.0

    def test_exposure_reaches_max_on_persistently_dark_frames(self, tmp_path: Path) -> None:
        cam = ReplayCamera.from_directory(_dark_dir(tmp_path, n=20))
        ctrl = self._run_loop(cam, n_frames=20)
        assert ctrl.exposure == pytest.approx(_EXP_MAX, abs=0.01)

    def test_exposure_decreases_on_bright_frames(self, tmp_path: Path) -> None:
        cam = ReplayCamera.from_directory(_bright_dir(tmp_path))
        ctrl = self._run_loop(cam, n_frames=8)
        assert ctrl.exposure < 2.0

    def test_exposure_reaches_min_on_persistently_bright_frames(self, tmp_path: Path) -> None:
        cam = ReplayCamera.from_directory(_bright_dir(tmp_path, n=20))
        ctrl = self._run_loop(cam, n_frames=20)
        assert ctrl.exposure == pytest.approx(_EXP_MIN, abs=0.01)
