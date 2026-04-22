from abc import ABC, abstractmethod

from ..domain.frame import FitsFrame


class CameraPort(ABC):
    @abstractmethod
    def connect(self) -> bool: ...

    @abstractmethod
    def capture(self, exposure_seconds: float) -> FitsFrame: ...

    @abstractmethod
    def disconnect(self) -> None: ...
