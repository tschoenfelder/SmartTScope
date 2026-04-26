from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..domain.frame import FitsFrame


@dataclass
class StackedImage:
    data: bytes
    frames_integrated: int
    frames_rejected: int


class StackerPort(ABC):
    @abstractmethod
    def reset(self) -> None: ...

    @abstractmethod
    def add_frame(self, frame: FitsFrame, frame_number: int) -> StackedImage: ...

    @abstractmethod
    def get_current_stack(self) -> StackedImage: ...
