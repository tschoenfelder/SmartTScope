"""API for the guided "Observe" screen — GET /api/observing/state, POST /api/observing/intent.

This is the *only* endpoint pair the main-flow UI is allowed to call to move
the session forward (REQ-UX-004): the frontend sends an Intent and renders
whatever phase/guards/primary_action comes back — it never decides the next
step itself. Existing granular endpoints (/api/mount/goto, /api/polar/*, etc.)
stay registered for the separate Maintenance screen and for internal use by
ObservingService itself.
"""

from __future__ import annotations

import contextlib
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import config
from ..domain.observing_state import Intent
from ..ports.camera import CameraPort
from ..ports.focuser import FocuserPort
from ..ports.mount import MountPort
from ..ports.solver import SolverPort
from ..ports.stacker import StackerPort
from ..ports.storage import StoragePort
from ..services.device_state import DeviceStateService
from ..services.guiding_service import GuidingService
from ..services.hardware_coordinator import HardwareCommandCoordinator
from ..services.observing_service import ObservingDeps, ObservingService
from ..services.optical_train_registry import OpticalTrainRegistry
from ..workflow._types import C8_NATIVE, M42_DEC, M42_RA
from . import deps

router = APIRouter(prefix="/api/observing", tags=["observing"])


class IntentRequest(BaseModel):
    intent: str


class _LazyCamera:
    """Resolve the main camera on first use (M10-022).

    The state poll and intent post must never wait for camera bring-up —
    snapshot() and the early-phase intents (confirm context/home) don't touch
    the camera at all. Phase actions that do (polar capture, observation
    stages) run in background action threads, where resolving — and, if the
    M10-021 background connect is still running, briefly blocking — is fine.
    """

    def __init__(self) -> None:
        self._camera: CameraPort | None = None

    def __getattr__(self, name: str) -> Any:
        if self._camera is None:
            self._camera = deps.get_camera()
        return getattr(self._camera, name)


def _camera_readiness_payload() -> dict[str, Any] | None:
    """M10-002/M10-008: parallel camera identification for the Observe screen.

    Added at the API layer (not inside ObservingService.snapshot) so the
    mount-flow service stays camera-agnostic; None when the runtime service
    is unavailable (early startup, tests without a runtime).
    """
    try:
        snap = deps.get_camera_readiness().snapshot()
    except Exception:
        return None
    # M10-003: merge per-camera setup FSM state (phase, stars, exposure/gain)
    # into each identified role so the card renders from one payload.
    try:
        setup = deps.get_camera_setup().snapshot()
        for role, entry in snap.get("roles", {}).items():
            entry["setup"] = setup.get(role)
    except Exception:
        pass
    return snap


def _build_deps(
    camera: CameraPort,
    mount: MountPort,
    focuser: FocuserPort,
    solver: SolverPort,
    stacker: StackerPort,
    storage: StoragePort,
    coordinator: HardwareCommandCoordinator,
    device_state: DeviceStateService,
    guiding_service: GuidingService,
    registry: OpticalTrainRegistry,
) -> ObservingDeps:
    guide_role_cameras: dict[str, CameraPort] = {}
    guide_train = registry.guide() if registry is not None else None
    if guide_train is not None:
        # M10-022: never open a camera in a request thread — use the handle
        # only if something else (setup FSM, preview) already opened it.
        # Guiding needs it much later in the flow; by then it is open.
        with contextlib.suppress(Exception):
            cam = deps.peek_camera_by_role(guide_train.camera_role)
            if cam is not None:
                guide_role_cameras["guide"] = cam
    return ObservingDeps(
        camera=camera,
        mount=mount,
        focuser=focuser,
        solver=solver,
        stacker=stacker,
        storage=storage,
        coordinator=coordinator,
        device_state=device_state,
        guiding_service=guiding_service,
        optical_profile=C8_NATIVE,
        target_ra=M42_RA,
        target_dec=M42_DEC,
        guide_role_cameras=guide_role_cameras,
        observer_lat=config.OBSERVER_LAT,
        observer_lon=config.OBSERVER_LON,
        ha_east_limit_h=config.MOUNT_HA_EAST_LIMIT_H,
        ha_west_limit_h=config.MOUNT_HA_WEST_LIMIT_H,
    )


@router.get("/state")
def observing_state(
    mount: MountPort = Depends(deps.get_mount),
    focuser: FocuserPort = Depends(deps.get_focuser),
    solver: SolverPort = Depends(deps.get_solver),
    stacker: StackerPort = Depends(deps.get_stacker),
    storage: StoragePort = Depends(deps.get_storage),
    coordinator: HardwareCommandCoordinator = Depends(deps.get_coordinator),
    device_state: DeviceStateService = Depends(deps.get_device_state),
    guiding_service: GuidingService = Depends(deps.get_guiding_service),
    registry: OpticalTrainRegistry = Depends(deps.get_optical_train_registry),
    svc: ObservingService = Depends(deps.get_observing_service),
) -> dict[str, Any]:
    """Current phase, guard status, and the single suggested next action."""
    d = _build_deps(
        _LazyCamera(), mount, focuser, solver, stacker, storage,
        coordinator, device_state, guiding_service, registry,
    )
    snap = svc.snapshot(d)
    snap["cameras"] = _camera_readiness_payload()
    return snap


@router.post("/intent")
def observing_intent(
    body: IntentRequest,
    mount: MountPort = Depends(deps.get_mount),
    focuser: FocuserPort = Depends(deps.get_focuser),
    solver: SolverPort = Depends(deps.get_solver),
    stacker: StackerPort = Depends(deps.get_stacker),
    storage: StoragePort = Depends(deps.get_storage),
    coordinator: HardwareCommandCoordinator = Depends(deps.get_coordinator),
    device_state: DeviceStateService = Depends(deps.get_device_state),
    guiding_service: GuidingService = Depends(deps.get_guiding_service),
    registry: OpticalTrainRegistry = Depends(deps.get_optical_train_registry),
    svc: ObservingService = Depends(deps.get_observing_service),
) -> dict[str, Any]:
    """Send a user/system intent — the only way to move the observing phase forward."""
    try:
        intent = Intent(body.intent)
    except ValueError:
        valid = ", ".join(i.value for i in Intent)
        raise HTTPException(
            status_code=422, detail=f"Unknown intent {body.intent!r}. Valid: {valid}",
        ) from None
    d = _build_deps(
        _LazyCamera(), mount, focuser, solver, stacker, storage,
        coordinator, device_state, guiding_service, registry,
    )
    snap = svc.handle_intent(intent, d)
    snap["cameras"] = _camera_readiness_payload()
    return snap
