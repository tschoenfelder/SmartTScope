"""SimulatorCamera — CameraPort backed by stored real FITS frames.

Replaces live hardware when no camera is connected.  Unlike ReplayCamera
(which takes an explicit file list for testing), SimulatorCamera discovers
frames from a directory and optionally paces delivery to match exposure time,
making the main app behave as if a real camera were attached.
"""
from __future__ import annotations

import time
from dataclasses import replace
from pathlib import Path

from ...domain.camera_capabilities import CameraCapabilities, ConversionGain
from ...domain.frame import FitsFrame
from ...ports.camera import CameraPort

_FITS_GLOB = ("*.fits", "*.fit")

_SIM_CAPABILITIES = CameraCapabilities(
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


class SimulatorCamera(CameraPort):
    """CameraPort that serves real FITS frames from a local directory.

    Args:
        data_dir: directory containing the FITS reference frames.
        speed: fraction of the requested exposure time to sleep before
            returning each frame.  0.0 (default) = instant; 1.0 = real-time.
    """

    def __init__(self, data_dir: str | Path, speed: float = 0.0) -> None:
        if not 0.0 <= speed <= 1.0:
            raise ValueError(f"speed must be in [0.0, 1.0], got {speed}")
        self._data_dir = Path(data_dir)
        self._speed = speed
        self._frames: list[Path] = []
        self._index = 0
        self._exposure_ms: float = 2000.0
        self._gain: int = 100
        self._black_level: int = 0
        self._conversion_gain: ConversionGain = ConversionGain.LCG

    # ------------------------------------------------------------------
    # CameraPort
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        if not self._data_dir.is_dir():
            return False
        seen: set[Path] = set()
        for pattern in _FITS_GLOB:
            seen.update(self._data_dir.glob(pattern))
        if not seen:
            return False
        self._frames = sorted(seen)
        self._index = 0
        return True

    def capture(self, exposure_seconds: float) -> FitsFrame:
        if not self._frames:
            raise RuntimeError("SimulatorCamera not connected or no frames available")

        delay = self._speed * exposure_seconds
        if delay > 0.0:
            time.sleep(delay)

        path = self._frames[self._index % len(self._frames)]
        self._index += 1

        frame = FitsFrame.from_fits_bytes(path.read_bytes())
        return replace(frame, exposure_seconds=exposure_seconds)

    def disconnect(self) -> None:
        self._frames = []
        self._index = 0

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
        return _SIM_CAPABILITIES

    def get_serial_number(self) -> str:
        return ""

    def get_logical_name(self) -> str:
        return "SimulatorCamera"
