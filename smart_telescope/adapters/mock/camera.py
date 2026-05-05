from typing import Any

import numpy as np

from ...domain.camera_capabilities import CameraCapabilities, ConversionGain
from ...domain.frame import FitsFrame
from ...ports.camera import CameraPort


def _bright_pixels() -> np.ndarray[Any, np.dtype[Any]]:
    """64×64 noisy star field — high positive SNR for quality-filter tests."""
    rng = np.random.default_rng(42)
    pixels = rng.normal(100.0, 10.0, (64, 64)).astype(np.float32)
    n = 64 * 64 // 50
    pixels[rng.integers(0, 64, n), rng.integers(0, 64, n)] += 1000.0
    return pixels


def _dim_pixels() -> np.ndarray[Any, np.dtype[Any]]:
    """64×64 cloud-covered frame — SNR well below 30 % of _bright_pixels SNR."""
    rng = np.random.default_rng(99)
    pixels = rng.normal(100.0, 10.0, (64, 64)).astype(np.float32)
    n = 64 * 64 // 50
    pixels[rng.integers(0, 64, n), rng.integers(0, 64, n)] += 10.0
    return pixels


_MOCK_CAPABILITIES = CameraCapabilities(
    min_gain=100,
    max_gain=3200,
    min_exposure_ms=0.1,
    max_exposure_ms=60_000.0,
    supports_cooling=False,
    supports_hcg=False,
    supports_lcg=False,
    supports_hdr=False,
    supports_black_level=False,
    bit_depth=16,
    pixel_size_um=2.4,
    sensor_width_px=3096,
    sensor_height_px=2080,
)


class MockCamera(CameraPort):
    def __init__(
        self,
        fail_connect: bool = False,
        fail_on_capture: int | None = None,
        return_bright: bool = False,
        dim_on_captures: frozenset[int] | None = None,
    ) -> None:
        self._fail_connect = fail_connect
        self._fail_on_capture = fail_on_capture
        self._return_bright = return_bright
        self._dim_on_captures: frozenset[int] = dim_on_captures or frozenset()
        self._capture_count = 0
        self._exposure_ms: float = 2000.0
        self._gain: int = 100
        self._black_level: int = 0
        self._conversion_gain: ConversionGain = ConversionGain.LCG

    def connect(self) -> bool:
        return not self._fail_connect

    def capture(self, exposure_seconds: float) -> FitsFrame:
        self._capture_count += 1
        if self._fail_on_capture is not None and self._capture_count == self._fail_on_capture:
            raise RuntimeError(f"MockCamera: capture failed (call #{self._capture_count})")
        if self._capture_count in self._dim_on_captures:
            pixels: np.ndarray[Any, np.dtype[Any]] = _dim_pixels()
        elif self._return_bright:
            pixels = _bright_pixels()
        else:
            pixels = np.zeros((2080, 3096), dtype=np.float32)
        return FitsFrame(pixels=pixels, header={}, exposure_seconds=exposure_seconds)

    def disconnect(self) -> None:
        pass

    def get_exposure_ms(self) -> float:
        return self._exposure_ms

    def set_exposure_ms(self, ms: float) -> None:
        self._exposure_ms = max(0.1, ms)

    def get_gain(self) -> int:
        return self._gain

    def set_gain(self, gain: int) -> None:
        self._gain = max(100, gain)

    def get_black_level(self) -> int:
        return self._black_level

    def set_black_level(self, level: int) -> None:
        self._black_level = max(0, level)

    def get_conversion_gain(self) -> ConversionGain:
        return self._conversion_gain

    def set_conversion_gain(self, mode: ConversionGain) -> None:
        self._conversion_gain = mode

    def get_bit_depth(self) -> int:
        return 16

    def get_temperature(self) -> float | None:
        return None

    def get_capabilities(self) -> CameraCapabilities:
        return _MOCK_CAPABILITIES
