from abc import ABC, abstractmethod

from ..domain.camera_capabilities import CameraCapabilities, ConversionGain
from ..domain.frame import FitsFrame


class CameraPort(ABC):
    @abstractmethod
    def connect(self) -> bool: ...

    @abstractmethod
    def capture(self, exposure_seconds: float) -> FitsFrame: ...

    @abstractmethod
    def disconnect(self) -> None: ...

    @abstractmethod
    def get_exposure_ms(self) -> float: ...

    @abstractmethod
    def set_exposure_ms(self, ms: float) -> None: ...

    @abstractmethod
    def get_gain(self) -> int: ...

    @abstractmethod
    def set_gain(self, gain: int) -> None: ...

    @abstractmethod
    def get_black_level(self) -> int: ...

    @abstractmethod
    def set_black_level(self, level: int) -> None: ...

    @abstractmethod
    def get_conversion_gain(self) -> ConversionGain: ...

    @abstractmethod
    def set_conversion_gain(self, mode: ConversionGain) -> None: ...

    @abstractmethod
    def get_bit_depth(self) -> int: ...

    @abstractmethod
    def get_temperature(self) -> float | None: ...

    @abstractmethod
    def get_capabilities(self) -> CameraCapabilities: ...

    @abstractmethod
    def get_serial_number(self) -> str: ...

    @abstractmethod
    def get_logical_name(self) -> str: ...
