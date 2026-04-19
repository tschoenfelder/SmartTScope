from pathlib import Path

from ...ports.camera import CameraPort, Frame


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
        if missing:
            raise FileNotFoundError(f"ReplayCamera: fixture(s) not found: {missing}")
        return True

    def capture(self, exposure_seconds: float) -> Frame:
        path = self._paths[self._index % len(self._paths)]
        self._index += 1
        data = path.read_bytes()
        return Frame(data=data, width=0, height=0, exposure_seconds=exposure_seconds)

    def disconnect(self) -> None:
        pass
