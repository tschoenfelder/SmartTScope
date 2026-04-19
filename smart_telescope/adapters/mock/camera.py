from typing import Optional

from ...ports.camera import CameraPort, Frame


class MockCamera(CameraPort):
    def __init__(
        self,
        fail_connect: bool = False,
        fail_on_capture: Optional[int] = None,
    ) -> None:
        self._fail_connect = fail_connect
        self._fail_on_capture = fail_on_capture
        self._capture_count = 0

    def connect(self) -> bool:
        return not self._fail_connect

    def capture(self, exposure_seconds: float) -> Frame:
        self._capture_count += 1
        if self._fail_on_capture is not None and self._capture_count == self._fail_on_capture:
            raise RuntimeError(f"MockCamera: capture failed (call #{self._capture_count})")
        return Frame(data=b"MOCK_FITS", width=3096, height=2080, exposure_seconds=exposure_seconds)

    def disconnect(self) -> None:
        pass
