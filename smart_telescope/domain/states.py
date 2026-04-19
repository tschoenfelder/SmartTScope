from enum import Enum, auto
from dataclasses import dataclass
from typing import Optional


class SessionState(Enum):
    IDLE = auto()
    CONNECTED = auto()
    MOUNT_READY = auto()
    ALIGNED = auto()
    SLEWED = auto()
    CENTERED = auto()            # centered within tolerance
    CENTERING_DEGRADED = auto()  # max iterations exceeded; session continues with warning
    PREVIEWING = auto()
    STACKING = auto()
    STACK_COMPLETE = auto()
    SAVED = auto()
    FAILED = auto()


@dataclass
class ConnectResult:
    success: bool
    camera_ok: bool = False
    mount_ok: bool = False
    failure_reason: Optional[str] = None


@dataclass
class MountReadyResult:
    success: bool
    was_parked: bool = False
    tracking_enabled: bool = False
    failure_reason: Optional[str] = None


@dataclass
class AlignmentResult:
    success: bool
    ra: float = 0.0
    dec: float = 0.0
    attempts: int = 0
    failure_reason: Optional[str] = None


@dataclass
class SlewResult:
    success: bool
    target_ra: float = 0.0
    target_dec: float = 0.0
    failure_reason: Optional[str] = None


@dataclass
class CenteringResult:
    success: bool
    iterations: int = 0
    final_offset_arcmin: float = 0.0
    max_iterations_reached: bool = False
    failure_reason: Optional[str] = None


@dataclass
class PreviewResult:
    success: bool
    frames_sent: int = 0
    failure_reason: Optional[str] = None


@dataclass
class StackResult:
    success: bool
    frames_integrated: int = 0
    frames_rejected: int = 0
    failure_reason: Optional[str] = None


@dataclass
class SaveResult:
    success: bool
    image_path: Optional[str] = None
    log_path: Optional[str] = None
    failure_reason: Optional[str] = None
