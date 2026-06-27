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

from typing import TYPE_CHECKING

from fastapi import HTTPException

if TYPE_CHECKING:
    from ..services.guiding_service import GuidingService

from ..ports.camera import CameraPort
from ..ports.focuser import FocuserPort
from ..ports.mount import MountPort
from ..ports.solver import SolverPort
from ..ports.stacker import StackerPort
from ..ports.storage import StoragePort
from ..runtime import RuntimeContext
from ..runtime import get_runtime as _get_runtime
from ..services.cooling import CoolingService
from ..services.hardware_coordinator import HardwareCommandCoordinator
from ..services.device_state import DeviceStateService
from ..services.job_manager import JobManager
from ..services.master_source import MasterSourceService
from ..services.raspberry_time_trust import RaspberryTimeTrustService
from ..services.optical_train_registry import OpticalTrainRegistry


def get_runtime() -> RuntimeContext:
    """FastAPI-injectable wrapper around the global runtime singleton."""
    return _get_runtime()


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


def get_cooling_service() -> CoolingService:
    return get_runtime().cooling_service


def get_coordinator() -> HardwareCommandCoordinator:
    return get_runtime().coordinator


def get_device_state() -> DeviceStateService:
    return get_runtime().device_state


def get_master_source_service() -> MasterSourceService:
    return get_runtime().master_source_svc


def get_raspberry_trust_service() -> RaspberryTimeTrustService:
    return get_runtime().raspberry_trust_svc


def get_job_manager() -> JobManager:
    return get_runtime().job_manager


def get_optical_train_registry() -> OpticalTrainRegistry:
    return get_runtime().get_optical_train_registry()  # type: ignore[return-value]


def reset() -> None:
    """Reset all cached singletons (used in tests)."""
    get_runtime().reset_for_tests()


def resolve_camera_index(camera_index: int, camera_role: str | None) -> int:
    """Resolve camera_role → camera_index when role is provided; otherwise pass camera_index through.

    Raises HTTPException 422 if camera_role is provided but not found in the registry.
    """
    if not camera_role:
        return camera_index
    registry = get_optical_train_registry()
    train = registry.by_camera_role(camera_role)
    if train is None:
        raise HTTPException(
            status_code=422,
            detail=f"camera_role {camera_role!r} not found in optical train registry",
        )
    return train.camera_index


def get_guiding_service() -> GuidingService:
    """Return the lazily-created GuidingService from the runtime context."""
    return get_runtime().guiding_service


def get_command_history_service() -> "CommandHistoryService":
    return get_runtime().command_history


def get_section_logger() -> "SectionLogger":
    return get_runtime().section_logger


def get_service_call_logger() -> "ServiceCallLogger":
    return get_runtime().service_call_logger


def get_user_action_logger() -> "UserActionLogger":
    return get_runtime().user_action_logger


def get_diagnostic_frame_store() -> "DiagnosticFrameStore":
    return get_runtime().diagnostic_frame_store
