"""Unit tests for ReplayCamera — exercised without hardware."""
from pathlib import Path

import pytest

from smart_telescope.adapters.replay.camera import ReplayCamera


def _write_fits(tmp: Path, name: str = "frame.fits") -> Path:
    p = tmp / name
    p.write_bytes(b"FAKE_FITS_DATA")
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
    def test_capture_returns_frame_with_correct_bytes(self, tmp_path: Path) -> None:
        f = _write_fits(tmp_path)
        cam = ReplayCamera([str(f)])
        frame = cam.capture(5.0)
        assert frame.data == b"FAKE_FITS_DATA"

    def test_capture_records_exposure(self, tmp_path: Path) -> None:
        f = _write_fits(tmp_path)
        cam = ReplayCamera([str(f)])
        frame = cam.capture(30.0)
        assert frame.exposure_seconds == pytest.approx(30.0)

    def test_capture_cycles_through_multiple_files(self, tmp_path: Path) -> None:
        f1 = _write_fits(tmp_path, "a.fits")
        f2 = _write_fits(tmp_path, "b.fits")
        f2.write_bytes(b"SECOND")
        cam = ReplayCamera([str(f1), str(f2)])
        cam.capture(1.0)
        frame2 = cam.capture(1.0)
        assert frame2.data == b"SECOND"

    def test_disconnect_is_safe_to_call(self, tmp_path: Path) -> None:
        f = _write_fits(tmp_path)
        cam = ReplayCamera([str(f)])
        cam.disconnect()
