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
    def guide(self, direction: str, duration_ms: int) -> bool:
        """Send a fixed-duration guide pulse.

        direction: 'n' | 's' | 'e' | 'w'
        duration_ms: pulse length in milliseconds (1–9999)
        """
        ...

    @abstractmethod
    def start_alignment(self, num_stars: int) -> bool:
        """Initialise n-star alignment sequence (num_stars: 1–9)."""
        ...

    @abstractmethod
    def accept_alignment_star(self) -> bool:
        """Record the current pointing direction as an alignment star."""
        ...

    @abstractmethod
    def save_alignment(self) -> bool:
        """Write the computed pointing model to EEPROM."""
        ...

    def get_park_position(self) -> MountPosition | None:
        """Return the stored park position, or None if the adapter doesn't support it."""
        return None

    @abstractmethod
    def disconnect(self) -> None: ...
