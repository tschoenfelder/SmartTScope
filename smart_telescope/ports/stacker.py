from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class StackFrame:
    data: bytes
    frame_number: int


@dataclass
class StackedImage:
    data: bytes
    frames_integrated: int
    frames_rejected: int


class StackerPort(ABC):
    @abstractmethod
    def reset(self) -> None: ...

    @abstractmethod
    def add_frame(self, frame: StackFrame) -> StackedImage: ...

    @abstractmethod
    def get_current_stack(self) -> StackedImage: ...
