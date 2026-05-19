"""Unit tests for ReplayCamera — exercised without hardware."""
import io
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits

from smart_telescope.adapters.replay.camera import ReplayCamera
from smart_telescope.domain.frame import FitsFrame


def _write_fits(
    tmp: Path,
    name: str = "frame.fits",
    width: int = 40,
    height: int = 30,
) -> Path:
    """Write a minimal valid FITS file with known dimensions."""
    hdu = fits.PrimaryHDU(np.zeros((height, width), dtype=np.uint16))
    buf = io.BytesIO()
    hdu.writeto(buf)
    p = tmp / name
    p.write_bytes(buf.getvalue())
    return p


class TestReplayCameraConnect:
    def test_connect_true_when_all_files_exist(self, tmp_path: Path) -> None:
        f = _write_fits(tmp_path)
        cam = ReplayCamera([str(f)])
        assert cam.connect() is True

    def test_connect_false_when_file_missing(self) -> None:
        cam = ReplayCamera(["/nonexistent/frame.fits"])
        assert cam.connect() is False

    def test_requires_at_least_one_path(self) -> None:
        with pytest.raises(ValueError):
            ReplayCamera([])


class TestReplayCameraCapture:
    def test_capture_returns_fits_frame(self, tmp_path: Path) -> None:
        f = _write_fits(tmp_path)
        cam = ReplayCamera([str(f)])
        assert isinstance(cam.capture(5.0), FitsFrame)

    def test_capture_pixel_dimensions_match_fits_image(self, tmp_path: Path) -> None:
        f = _write_fits(tmp_path, width=120, height=80)
        cam = ReplayCamera([str(f)])
        frame = cam.capture(5.0)
        assert frame.width == 120
        assert frame.height == 80

    def test_capture_records_exposure(self, tmp_path: Path) -> None:
        f = _write_fits(tmp_path)
        cam = ReplayCamera([str(f)])
        frame = cam.capture(30.0)
        assert frame.exposure_seconds == pytest.approx(30.0)

    def test_capture_raw_bytes_stored_in_data(self, tmp_path: Path) -> None:
        f = _write_fits(tmp_path)
        cam = ReplayCamera([str(f)])
        frame = cam.capture(5.0)
        assert frame.data == f.read_bytes()

    def test_capture_pixels_dtype_is_float32(self, tmp_path: Path) -> None:
        f = _write_fits(tmp_path)
        cam = ReplayCamera([str(f)])
        frame = cam.capture(5.0)
        assert frame.pixels.dtype == np.float32

    def test_capture_cycles_through_multiple_files(self, tmp_path: Path) -> None:
        f1 = _write_fits(tmp_path, "a.fits", width=40, height=30)
        f2 = _write_fits(tmp_path, "b.fits", width=60, height=50)
        cam = ReplayCamera([str(f1), str(f2)])
        cam.capture(1.0)
        frame2 = cam.capture(1.0)
        assert frame2.width == 60
        assert frame2.height == 50

    def test_disconnect_is_safe_to_call(self, tmp_path: Path) -> None:
        f = _write_fits(tmp_path)
        cam = ReplayCamera([str(f)])
        cam.disconnect()
