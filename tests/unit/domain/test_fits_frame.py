"""
Unit tests for FitsFrame — the typed domain object that replaces Frame(data: bytes).

TDD step: RED — these tests fail until smart_telescope/domain/frame.py is implemented.

Design contract being tested:
  - FitsFrame carries pixels (np.ndarray float32), a parsed FITS Header, and exposure_seconds.
  - FitsFrame.from_fits_bytes() parses raw FITS bytes from the camera driver.
  - FitsFrame is immutable (frozen dataclass) — no accidental in-place mutation.
  - width and height are derived from the pixel array shape, not stored separately.
  - exposure_seconds is read from the FITS EXPTIME header key; defaults to 0.0 if absent.
"""

import io

import numpy as np
import pytest

# These imports will fail (RED) until the domain type is implemented.
from smart_telescope.domain.frame import FitsFrame

try:
    from astropy.io import fits
    from astropy.io.fits import Header
    HAS_ASTROPY = True
except ImportError:
    HAS_ASTROPY = False

pytestmark = pytest.mark.skipif(not HAS_ASTROPY, reason="astropy not installed")


# ── helpers ────────────────────────────────────────────────────────────────────

def _make_fits_bytes(
    width: int = 120,
    height: int = 80,
    exptime: float = 10.0,
    dtype: type = np.uint16,
) -> bytes:
    """Create minimal valid FITS bytes with a known pixel array and EXPTIME."""
    pixels = np.arange(width * height, dtype=dtype).reshape(height, width)
    hdu = fits.PrimaryHDU(pixels)
    hdu.header["EXPTIME"] = exptime
    buf = io.BytesIO()
    hdu.writeto(buf)
    return buf.getvalue()


def _make_fits_bytes_no_exptime(width: int = 40, height: int = 30) -> bytes:
    """FITS bytes with no EXPTIME header key — exptime should default to 0.0."""
    hdu = fits.PrimaryHDU(np.zeros((height, width), dtype=np.uint16))
    buf = io.BytesIO()
    hdu.writeto(buf)
    return buf.getvalue()


# ── Construction ───────────────────────────────────────────────────────────────

class TestFitsFrameConstruction:
    def test_pixels_stored_as_provided(self):
        pixels = np.zeros((80, 120), dtype=np.float32)
        header = Header()
        frame = FitsFrame(pixels=pixels, header=header, exposure_seconds=5.0)
        assert frame.pixels is pixels

    def test_header_stored_as_provided(self):
        pixels = np.zeros((80, 120), dtype=np.float32)
        header = Header()
        header["EXPTIME"] = 7.5
        frame = FitsFrame(pixels=pixels, header=header, exposure_seconds=7.5)
        assert frame.header is header

    def test_exposure_seconds_stored(self):
        frame = FitsFrame(
            pixels=np.zeros((10, 10), dtype=np.float32),
            header=Header(),
            exposure_seconds=30.0,
        )
        assert frame.exposure_seconds == 30.0


# ── width / height properties ─────────────────────────────────────────────────

class TestFitsFrameDimensions:
    def test_width_matches_pixel_array_columns(self):
        frame = FitsFrame(
            pixels=np.zeros((80, 120), dtype=np.float32),
            header=Header(),
            exposure_seconds=0.0,
        )
        assert frame.width == 120

    def test_height_matches_pixel_array_rows(self):
        frame = FitsFrame(
            pixels=np.zeros((80, 120), dtype=np.float32),
            header=Header(),
            exposure_seconds=0.0,
        )
        assert frame.height == 80

    def test_width_and_height_are_ints(self):
        frame = FitsFrame(
            pixels=np.zeros((50, 75), dtype=np.float32),
            header=Header(),
            exposure_seconds=0.0,
        )
        assert isinstance(frame.width, int)
        assert isinstance(frame.height, int)

    @pytest.mark.parametrize("h, w", [(1, 1), (2080, 3096), (480, 640)])
    def test_dimensions_match_array_for_common_sensor_sizes(self, h: int, w: int):
        frame = FitsFrame(
            pixels=np.zeros((h, w), dtype=np.float32),
            header=Header(),
            exposure_seconds=0.0,
        )
        assert frame.height == h
        assert frame.width == w


# ── Immutability ───────────────────────────────────────────────────────────────

class TestFitsFrameImmutability:
    def test_pixels_field_cannot_be_reassigned(self):
        frame = FitsFrame(
            pixels=np.zeros((10, 10), dtype=np.float32),
            header=Header(),
            exposure_seconds=0.0,
        )
        with pytest.raises((AttributeError, TypeError)):
            frame.pixels = np.ones((10, 10), dtype=np.float32)  # type: ignore[misc]

    def test_exposure_seconds_cannot_be_reassigned(self):
        frame = FitsFrame(
            pixels=np.zeros((10, 10), dtype=np.float32),
            header=Header(),
            exposure_seconds=5.0,
        )
        with pytest.raises((AttributeError, TypeError)):
            frame.exposure_seconds = 99.0  # type: ignore[misc]


# ── from_fits_bytes ────────────────────────────────────────────────────────────

class TestFitsFrameFromFitsBytes:
    def test_pixels_shape_matches_fits_image_dimensions(self):
        raw = _make_fits_bytes(width=120, height=80)
        frame = FitsFrame.from_fits_bytes(raw)
        assert frame.pixels.shape == (80, 120)

    def test_pixels_dtype_is_float32(self):
        raw = _make_fits_bytes(width=60, height=40)
        frame = FitsFrame.from_fits_bytes(raw)
        assert frame.pixels.dtype == np.float32

    def test_exposure_seconds_read_from_exptime_header(self):
        raw = _make_fits_bytes(exptime=30.0)
        frame = FitsFrame.from_fits_bytes(raw)
        assert frame.exposure_seconds == pytest.approx(30.0)

    def test_exposure_seconds_defaults_to_zero_when_exptime_absent(self):
        raw = _make_fits_bytes_no_exptime()
        frame = FitsFrame.from_fits_bytes(raw)
        assert frame.exposure_seconds == 0.0

    def test_header_contains_exptime_key(self):
        raw = _make_fits_bytes(exptime=15.0)
        frame = FitsFrame.from_fits_bytes(raw)
        assert "EXPTIME" in frame.header

    def test_pixel_values_preserved_from_source_image(self):
        raw = _make_fits_bytes(width=4, height=3)
        frame = FitsFrame.from_fits_bytes(raw)
        # arange fills 0…11 across 3×4; verify at least min/max survive conversion
        assert frame.pixels.min() == pytest.approx(0.0)
        assert frame.pixels.max() == pytest.approx(11.0)

    def test_returns_fits_frame_instance(self):
        raw = _make_fits_bytes()
        assert isinstance(FitsFrame.from_fits_bytes(raw), FitsFrame)

    def test_invalid_bytes_raises_value_error(self):
        with pytest.raises((ValueError, OSError)):
            FitsFrame.from_fits_bytes(b"not a fits file at all")


# ── Port contract — CameraPort returns FitsFrame ──────────────────────────────

class TestCameraPortContract:
    """After migration: CameraPort.capture() must return FitsFrame, not Frame."""

    def test_mock_camera_capture_returns_fits_frame(self):
        from smart_telescope.adapters.mock.camera import MockCamera
        cam = MockCamera()
        cam.connect()
        result = cam.capture(5.0)
        assert isinstance(result, FitsFrame), (
            f"MockCamera.capture() returned {type(result).__name__}, expected FitsFrame"
        )

    def test_mock_camera_frame_has_correct_exposure(self):
        from smart_telescope.adapters.mock.camera import MockCamera
        cam = MockCamera()
        cam.connect()
        frame = cam.capture(exposure_seconds=10.0)
        assert frame.exposure_seconds == pytest.approx(10.0)

    def test_mock_camera_frame_has_non_zero_dimensions(self):
        from smart_telescope.adapters.mock.camera import MockCamera
        cam = MockCamera()
        cam.connect()
        frame = cam.capture(5.0)
        assert frame.width > 0
        assert frame.height > 0
