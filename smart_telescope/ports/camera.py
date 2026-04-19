from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class Frame:
    data: bytes
    width: int
    height: int
    exposure_seconds: float


class CameraPort(ABC):
    @abstractmethod
    def connect(self) -> bool: ...

    @abstractmethod
    def capture(self, exposure_seconds: float) -> Frame: ...

    @abstractmethod
    def disconnect(self) -> None: ...
