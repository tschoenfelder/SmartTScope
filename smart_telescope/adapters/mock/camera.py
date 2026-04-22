from typing import Any

import numpy as np

from ...domain.frame import FitsFrame
from ...ports.camera import CameraPort


class MockCamera(CameraPort):
    def __init__(
        self,
        fail_connect: bool = False,
        fail_on_capture: int | None = None,
    ) -> None:
        self._fail_connect = fail_connect
        self._fail_on_capture = fail_on_capture
        self._capture_count = 0

    def connect(self) -> bool:
        return not self._fail_connect

    def capture(self, exposure_seconds: float) -> FitsFrame:
        self._capture_count += 1
        if self._fail_on_capture is not None and self._capture_count == self._fail_on_capture:
            raise RuntimeError(f"MockCamera: capture failed (call #{self._capture_count})")
        pixels: np.ndarray[Any, np.dtype[Any]] = np.zeros((2080, 3096), dtype=np.float32)
        return FitsFrame(pixels=pixels, header={}, exposure_seconds=exposure_seconds)

    def disconnect(self) -> None:
        pass
