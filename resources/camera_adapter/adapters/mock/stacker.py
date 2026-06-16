from ...domain.frame import FitsFrame
from ...ports.stacker import StackedImage, StackerPort


class MockStacker(StackerPort):
    def __init__(self, fail_on_frame: int | None = None) -> None:
        self._count = 0
        self._fail_on_frame = fail_on_frame

    def reset(self) -> None:
        self._count = 0

    def add_frame(self, frame: FitsFrame, frame_number: int) -> StackedImage:
        if self._fail_on_frame is not None and frame_number == self._fail_on_frame:
            raise RuntimeError(f"MockStacker: failed on frame {frame_number}")
        self._count += 1
        return StackedImage(
            data=b"MOCK_STACK",
            frames_integrated=self._count,
            frames_rejected=0,
        )

    def get_current_stack(self) -> StackedImage:
        return StackedImage(
            data=b"MOCK_STACK",
            frames_integrated=self._count,
            frames_rejected=0,
        )
