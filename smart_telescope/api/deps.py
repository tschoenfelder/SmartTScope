"""FastAPI dependency providers — compatibility wrappers over RuntimeContext.

All adapter state now lives in RuntimeContext (smart_telescope/runtime.py).
These functions keep the existing FastAPI dependency-injection API stable so
that API modules and tests require no changes during the R0 migration.

Adapter selection priority (documented in RuntimeContext._build_adapters):

  Camera:
    [cameras] main configured  → ToupcamCamera(index=CAMERAS["main"])
    TOUPTEK_INDEX env var       → ToupcamCamera(index=int(TOUPTEK_INDEX))  (legacy)
    SIMULATOR_FITS_DIR          → SimulatorCamera
    REPLAY_FITS_DIR             → ReplayCamera.from_directory
    (none of the above)         → MockCamera (unit-test default)

  Named camera roles (config [cameras] section):
    main  — primary imaging camera at the C8
    guide — guide camera on the 180×50 guide scope
    atr   — ATR585M at the C8 (optional; when present, main/678M acts as OAG)

  Mount + Focuser:
    ONSTEP_PORT set    → OnStepMount + OnStepFocuser (real hardware)
    SIMULATOR_FITS_DIR → SimulatorMount + SimulatorFocuser
    (neither)          → MockMount + MockFocuser (unit-test default)
"""

from __future__ import annotations

from ..ports.camera import CameraPort
from ..ports.focuser import FocuserPort
from ..ports.mount import MountPort
from ..ports.solver import SolverPort
from ..ports.stacker import StackerPort
from ..ports.storage import StoragePort
from ..runtime import get_runtime
from ..services.hardware_coordinator import HardwareCommandCoordinator
from ..services.device_state import DeviceStateService
from ..services.job_manager import JobManager


def get_camera() -> CameraPort:
    return get_runtime().get_camera()


def get_preview_camera(index: int) -> CameraPort:
    return get_runtime().get_preview_camera(index)


def get_camera_by_role(role: str) -> CameraPort:
    return get_runtime().get_camera_by_role(role)


def get_mount() -> MountPort:
    return get_runtime().get_mount()


def get_focuser() -> FocuserPort:
    return get_runtime().get_focuser()


def get_stacker() -> StackerPort:
    return get_runtime().get_stacker()


def make_stacker() -> StackerPort:
    """Create a fresh stacker instance — used by the queue runner (one per session)."""
    return get_runtime().make_stacker()


def get_solver() -> SolverPort:
    return get_runtime().get_solver()


def get_storage() -> StoragePort:
    return get_runtime().get_storage()


def get_coordinator() -> HardwareCommandCoordinator:
    return get_runtime().coordinator


def get_device_state() -> DeviceStateService:
    return get_runtime().device_state


def get_job_manager() -> JobManager:
    return get_runtime().job_manager


def reset() -> None:
    """Reset all cached singletons (used in tests)."""
    get_runtime().reset_for_tests()
