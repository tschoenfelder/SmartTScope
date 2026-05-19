"""Unit tests for SimulatorCamera."""
import io
import time
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits

from smart_telescope.adapters.simulator.camera import SimulatorCamera
from smart_telescope.domain.frame import FitsFrame

# ── helpers ────────────────────────────────────────────────────────────────────


def _write_fits(
    tmp: Path,
    name: str = "frame.fits",
    width: int = 40,
    height: int = 30,
    exptime: float = 10.0,
) -> Path:
    hdu = fits.PrimaryHDU(np.zeros((height, width), dtype=np.uint16))
    hdu.header["EXPTIME"] = exptime
    buf = io.BytesIO()
    hdu.writeto(buf)
    p = tmp / name
    p.write_bytes(buf.getvalue())
    return p


def _populated(tmp_path: Path, count: int = 1, **kwargs: object) -> Path:
    for i in range(count):
        _write_fits(tmp_path, f"frame_{i:03d}.fits", **kwargs)  # type: ignore[arg-type]
    return tmp_path


# ── constructor ────────────────────────────────────────────────────────────────


class TestConstructor:
    def test_invalid_speed_raises(self) -> None:
        with pytest.raises(ValueError, match="speed"):
            SimulatorCamera("/tmp", speed=1.1)

    def test_negative_speed_raises(self) -> None:
        with pytest.raises(ValueError, match="speed"):
            SimulatorCamera("/tmp", speed=-0.1)

    def test_boundary_speeds_accepted(self) -> None:
        SimulatorCamera("/tmp", speed=0.0)
        SimulatorCamera("/tmp", speed=1.0)


# ── connect ────────────────────────────────────────────────────────────────────


class TestConnect:
    def test_false_when_directory_missing(self) -> None:
        cam = SimulatorCamera("/nonexistent/path")
        assert cam.connect() is False

    def test_false_when_directory_empty(self, tmp_path: Path) -> None:
        cam = SimulatorCamera(tmp_path)
        assert cam.connect() is False

    def test_false_when_no_fits_files(self, tmp_path: Path) -> None:
        (tmp_path / "readme.txt").write_text("hello")
        cam = SimulatorCamera(tmp_path)
        assert cam.connect() is False

    def test_true_when_fits_file_present(self, tmp_path: Path) -> None:
        _write_fits(tmp_path)
        cam = SimulatorCamera(tmp_path)
        assert cam.connect() is True

    def test_accepts_dot_fit_extension(self, tmp_path: Path) -> None:
        _write_fits(tmp_path, "frame.fit")
        cam = SimulatorCamera(tmp_path)
        assert cam.connect() is True

    def test_discovers_multiple_files(self, tmp_path: Path) -> None:
        _populated(tmp_path, count=5)
        cam = SimulatorCamera(tmp_path)
        assert cam.connect() is True


# ── capture ────────────────────────────────────────────────────────────────────


class TestCapture:
    def test_returns_fits_frame(self, tmp_path: Path) -> None:
        _write_fits(tmp_path)
        cam = SimulatorCamera(tmp_path)
        cam.connect()
        assert isinstance(cam.capture(5.0), FitsFrame)

    def test_pixel_dimensions_match_file(self, tmp_path: Path) -> None:
        _write_fits(tmp_path, width=120, height=80)
        cam = SimulatorCamera(tmp_path)
        cam.connect()
        frame = cam.capture(5.0)
        assert frame.width == 120
        assert frame.height == 80

    def test_exposure_seconds_overrides_file_header(self, tmp_path: Path) -> None:
        _write_fits(tmp_path, exptime=10.0)
        cam = SimulatorCamera(tmp_path)
        cam.connect()
        frame = cam.capture(30.0)
        assert frame.exposure_seconds == pytest.approx(30.0)

    def test_pixels_dtype_float32(self, tmp_path: Path) -> None:
        _write_fits(tmp_path)
        cam = SimulatorCamera(tmp_path)
        cam.connect()
        assert cam.capture(1.0).pixels.dtype == np.float32

    def test_cycles_through_multiple_files(self, tmp_path: Path) -> None:
        _write_fits(tmp_path, "a.fits", width=40, height=30)
        _write_fits(tmp_path, "b.fits", width=60, height=50)
        cam = SimulatorCamera(tmp_path)
        cam.connect()
        cam.capture(1.0)                  # a.fits (index 0)
        frame = cam.capture(1.0)          # b.fits (index 1)
        assert frame.width == 60

    def test_wraps_back_to_first_frame(self, tmp_path: Path) -> None:
        _write_fits(tmp_path, "a.fits", width=40, height=30)
        _write_fits(tmp_path, "b.fits", width=60, height=50)
        cam = SimulatorCamera(tmp_path)
        cam.connect()
        cam.capture(1.0)  # a
        cam.capture(1.0)  # b
        frame = cam.capture(1.0)  # wraps → a
        assert frame.width == 40

    def test_speed_zero_returns_instantly(self, tmp_path: Path) -> None:
        _write_fits(tmp_path)
        cam = SimulatorCamera(tmp_path, speed=0.0)
        cam.connect()
        t0 = time.monotonic()
        cam.capture(10.0)
        assert time.monotonic() - t0 < 0.5

    def test_speed_delays_proportionally(self, tmp_path: Path) -> None:
        _write_fits(tmp_path)
        cam = SimulatorCamera(tmp_path, speed=1.0)
        cam.connect()
        t0 = time.monotonic()
        cam.capture(0.1)
        elapsed = time.monotonic() - t0
        assert elapsed == pytest.approx(0.1, abs=0.05)

    def test_raises_when_not_connected(self, tmp_path: Path) -> None:
        cam = SimulatorCamera(tmp_path)
        with pytest.raises(RuntimeError, match="not connected"):
            cam.capture(1.0)


# ── disconnect ─────────────────────────────────────────────────────────────────


class TestDisconnect:
    def test_safe_before_connect(self, tmp_path: Path) -> None:
        SimulatorCamera(tmp_path).disconnect()

    def test_safe_after_connect(self, tmp_path: Path) -> None:
        _write_fits(tmp_path)
        cam = SimulatorCamera(tmp_path)
        cam.connect()
        cam.disconnect()

    def test_reconnect_resets_frame_index(self, tmp_path: Path) -> None:
        _write_fits(tmp_path, "a.fits", width=40, height=30)
        _write_fits(tmp_path, "b.fits", width=60, height=50)
        cam = SimulatorCamera(tmp_path)
        cam.connect()
        cam.capture(1.0)  # advances index to 1
        cam.disconnect()
        cam.connect()
        frame = cam.capture(1.0)  # should restart at index 0 → a.fits
        assert frame.width == 40

    def test_capture_fails_after_disconnect(self, tmp_path: Path) -> None:
        _write_fits(tmp_path)
        cam = SimulatorCamera(tmp_path)
        cam.connect()
        cam.disconnect()
        with pytest.raises(RuntimeError, match="not connected"):
            cam.capture(1.0)
