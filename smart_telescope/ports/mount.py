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
    AT_HOME = auto()


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
    def move(self, direction: str, move_ms: int) -> bool:
        """Move at center rate for move_ms milliseconds, then stop.

        Uses OnStep's manual centering rate (much faster than guide rate) so
        movement is visually observable. Blocks for the requested duration.
        direction: 'n' | 's' | 'e' | 'w'
        move_ms: duration in milliseconds (50–5000)
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

    def ensure_time_location_synced(self) -> None:
        """Push current system time and configured observer location to the mount.

        Called automatically before GoTo operations.  The default is a no-op;
        adapters that require explicit time/location sync (e.g. OnStep) override this.
        Raises RuntimeError if the sync fails (e.g. system clock not trusted).
        """

    def get_sync_status(self) -> dict | None:
        """Return a dict describing time/location sync status, or None if unsupported.

        Keys when not None: time_available, time_delta_s, time_threshold_s, time_ok,
        location_available, onstep_lat, onstep_lon, cfg_lat, cfg_lon,
        lat_delta_deg, lon_delta_deg, location_ok.
        """
        return None

    def get_park_position(self) -> MountPosition | None:
        """Return the stored park position, or None if the adapter doesn't support it."""
        return None

    def set_park_position(self) -> bool:
        """Save the current mount position as the park position.

        Must be called once from the desired park position before park() will
        be accepted by OnStep (:hS# on LX200).  Returns True on success.
        """
        return False

    @abstractmethod
    def go_home(self) -> None:
        """Command the mount to slew to its stored home position.

        On OnStep this sends :hC# (Move to home — counterweight-down).
        The slew is fire-and-forget; poll get_state() for completion.
        """
        ...

    @abstractmethod
    def disconnect(self) -> None: ...
