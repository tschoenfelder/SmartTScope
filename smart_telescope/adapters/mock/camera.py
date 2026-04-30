from typing import Any

import numpy as np

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
