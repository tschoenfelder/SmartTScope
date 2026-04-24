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

from ...domain.frame import FitsFrame
from ...ports.camera import CameraPort

_FITS_GLOB = ("*.fits", "*.fit")


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
