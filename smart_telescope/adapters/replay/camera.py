from dataclasses import replace
from pathlib import Path

from ...domain.frame import FitsFrame
from ...ports.camera import CameraPort


class ReplayCamera(CameraPort):
    """
    Camera adapter that serves prerecorded FITS files from disk.

    Cycles through the provided list of paths.  Useful for integration
    tests that need real image data without live hardware.
    """

    def __init__(self, fits_paths: list[str]) -> None:
        if not fits_paths:
            raise ValueError("ReplayCamera requires at least one FITS path")
        self._paths = [Path(p) for p in fits_paths]
        self._index = 0

    def connect(self) -> bool:
        missing = [p for p in self._paths if not p.exists()]
        return not missing

    def capture(self, exposure_seconds: float) -> FitsFrame:
        path = self._paths[self._index % len(self._paths)]
        self._index += 1
        frame = FitsFrame.from_fits_bytes(path.read_bytes())
        return replace(frame, exposure_seconds=exposure_seconds)

    def disconnect(self) -> None:
        pass
