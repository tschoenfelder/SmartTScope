from typing import Optional

from ...ports.stacker import StackerPort, StackFrame, StackedImage


class MockStacker(StackerPort):
    def __init__(self, fail_on_frame: Optional[int] = None) -> None:
        self._frames: list = []
        self._fail_on_frame = fail_on_frame

    def reset(self) -> None:
        self._frames.clear()

    def add_frame(self, frame: StackFrame) -> StackedImage:
        if self._fail_on_frame is not None and frame.frame_number == self._fail_on_frame:
            raise RuntimeError(f"MockStacker: failed on frame {frame.frame_number}")
        self._frames.append(frame)
        return StackedImage(
            data=b"MOCK_STACK",
            frames_integrated=len(self._frames),
            frames_rejected=0,
        )

    def get_current_stack(self) -> StackedImage:
        return StackedImage(
            data=b"MOCK_STACK",
            frames_integrated=len(self._frames),
            frames_rejected=0,
        )
