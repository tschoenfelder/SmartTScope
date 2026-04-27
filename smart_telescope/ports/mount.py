from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum, auto


class MountState(Enum):
    UNKNOWN = auto()
    PARKED = auto()
    UNPARKED = auto()
    SLEWING = auto()
    TRACKING = auto()
    AT_LIMIT = auto()


@dataclass
class MountPosition:
    ra: float   # hours
    dec: float  # degrees


class MountPort(ABC):
    @abstractmethod
    def connect(self) -> bool: ...

    @abstractmethod
    def get_state(self) -> MountState: ...

    @abstractmethod
    def unpark(self) -> bool: ...

    @abstractmethod
    def enable_tracking(self) -> bool: ...

    @abstractmethod
    def get_position(self) -> MountPosition: ...

    @abstractmethod
    def sync(self, ra: float, dec: float) -> bool: ...

    @abstractmethod
    def goto(self, ra: float, dec: float) -> bool: ...

    @abstractmethod
    def is_slewing(self) -> bool: ...

    @abstractmethod
    def stop(self) -> None: ...

    @abstractmethod
    def park(self) -> bool: ...

    @abstractmethod
    def disable_tracking(self) -> bool: ...

    @abstractmethod
    def disconnect(self) -> None: ...
