"""
Shared fixtures for unit tests.

All port fixtures return Mock(spec=<Port>) pre-configured for the happy path.
Individual tests override specific attributes for the scenario under test.
Hand-rolled fakes (MockCamera, MockMount, …) stay in tests/integration/ — they
are not used in unit tests.
"""
import threading
from datetime import UTC, datetime
from typing import Any
from unittest.mock import Mock

import numpy as np
import pytest

from smart_telescope.domain.frame import FitsFrame
from smart_telescope.domain.session import SessionLog
from smart_telescope.domain.states import SessionState
from smart_telescope.ports.camera import CameraPort
from smart_telescope.ports.focuser import FocuserPort
from smart_telescope.ports.mount import MountPort, MountPosition, MountState
from smart_telescope.ports.solver import SolveResult, SolverPort
from smart_telescope.ports.stacker import StackedImage, StackerPort
from smart_telescope.ports.storage import StoragePort
from smart_telescope.workflow.runner import (
    C8_NATIVE,
    M42_DEC,
    M42_RA,
    VerticalSliceRunner,
)
from smart_telescope.workflow.stages import StageContext

# ── Primitive builders ─────────────────────────────────────────────────────


def make_frame(exposure: float = 5.0) -> FitsFrame:
    pixels: np.ndarray[Any, np.dtype[Any]] = np.zeros((2080, 3096), dtype=np.float32)
    return FitsFrame(pixels=pixels, header={}, exposure_seconds=exposure, data=b"FAKE_FITS")


def make_stacked(n: int = 1) -> StackedImage:
    return StackedImage(data=b"FAKE_STACK", frames_integrated=n, frames_rejected=0)


def make_log() -> SessionLog:
    return SessionLog(
        session_id="test-session-001",
        target_name="M42",
        target_ra=M42_RA,
        target_dec=M42_DEC,
        optical_config=C8_NATIVE.name,
        started_at=datetime(2026, 4, 21, 21, 0, 0, tzinfo=UTC),
    )


# ── Port fixtures — happy path by default ─────────────────────────────────


@pytest.fixture()
def camera_mock() -> Mock:
    cam = Mock(spec=CameraPort)
    cam.connect.return_value = True
    cam.capture.return_value = make_frame()
    return cam


@pytest.fixture()
def mount_mock() -> Mock:
    mnt = Mock(spec=MountPort)
    mnt.connect.return_value = True
    mnt.get_state.return_value = MountState.TRACKING
    mnt.unpark.return_value = True
    mnt.enable_tracking.return_value = True
    mnt.sync.return_value = True
    mnt.goto.return_value = True
    mnt.is_slewing.return_value = False
    mnt.get_position.return_value = MountPosition(ra=M42_RA, dec=M42_DEC)
    return mnt


@pytest.fixture()
def solver_mock() -> Mock:
    slv = Mock(spec=SolverPort)
    slv.solve.return_value = SolveResult(success=True, ra=M42_RA, dec=M42_DEC, pa=0.0)
    return slv


@pytest.fixture()
def stacker_mock() -> Mock:
    stk = Mock(spec=StackerPort)
    stk.add_frame.return_value = make_stacked(1)
    stk.get_current_stack.return_value = make_stacked(10)
    return stk


@pytest.fixture()
def storage_mock() -> Mock:
    sto = Mock(spec=StoragePort)
    sto.has_free_space.return_value = True
    sto.save_image.return_value = "/data/result.png"
    sto.save_log.return_value = "/data/log.json"
    return sto


@pytest.fixture()
def focuser_mock() -> Mock:
    foc = Mock(spec=FocuserPort)
    foc.connect.return_value = True
    foc.get_position.return_value = 0
    foc.is_moving.return_value = False
    return foc


# ── Runner factory ─────────────────────────────────────────────────────────


def _default_mocks(
    camera: Mock | None,
    mount: Mock | None,
    solver: Mock | None,
    stacker: Mock | None,
    storage: Mock | None,
    focuser: Mock | None,
) -> tuple[Mock, Mock, Mock, Mock, Mock, Mock]:
    cam = camera if camera is not None else Mock(spec=CameraPort, **{
        "connect.return_value": True,
        "capture.return_value": make_frame(),
    })
    mnt = mount if mount is not None else Mock(spec=MountPort, **{
        "connect.return_value": True,
        "get_state.return_value": MountState.TRACKING,
        "unpark.return_value": True,
        "enable_tracking.return_value": True,
        "sync.return_value": True,
        "goto.return_value": True,
        "is_slewing.return_value": False,
        "get_position.return_value": MountPosition(ra=M42_RA, dec=M42_DEC),
    })
    slv = solver if solver is not None else Mock(spec=SolverPort, **{
        "solve.return_value": SolveResult(success=True, ra=M42_RA, dec=M42_DEC),
    })
    stk = stacker if stacker is not None else Mock(spec=StackerPort, **{
        "add_frame.return_value": make_stacked(1),
        "get_current_stack.return_value": make_stacked(10),
    })
    sto = storage if storage is not None else Mock(spec=StoragePort, **{
        "has_free_space.return_value": True,
        "save_image.return_value": "/data/result.png",
        "save_log.return_value": "/data/log.json",
    })
    foc = focuser if focuser is not None else Mock(spec=FocuserPort, **{
        "connect.return_value": True,
        "get_position.return_value": 0,
        "is_moving.return_value": False,
    })
    return cam, mnt, slv, stk, sto, foc


def make_unit_runner(
    camera: Mock | None = None,
    mount: Mock | None = None,
    solver: Mock | None = None,
    stacker: Mock | None = None,
    storage: Mock | None = None,
    focuser: Mock | None = None,
    optical_profile=C8_NATIVE,
) -> VerticalSliceRunner:
    cam, mnt, slv, stk, sto, foc = _default_mocks(camera, mount, solver, stacker, storage, focuser)
    return VerticalSliceRunner(
        camera=cam,
        mount=mnt,
        solver=slv,
        stacker=stk,
        storage=sto,
        focuser=foc,
        optical_profile=optical_profile,
    )


def make_stage_ctx(
    camera: Mock | None = None,
    mount: Mock | None = None,
    solver: Mock | None = None,
    stacker: Mock | None = None,
    storage: Mock | None = None,
    focuser: Mock | None = None,
    optical_profile=C8_NATIVE,
    stop_event: threading.Event | None = None,
    on_transition=None,
    target_ra: float = M42_RA,
    target_dec: float = M42_DEC,
    stack_exposure_s: float = 30.0,
    stack_depth: int = 10,
    preview_exposure_s: float = 5.0,
    preview_frames: int = 3,
    autofocus_range_steps: int = 200,
    autofocus_step_size: int = 20,
    autofocus_exposure_s: float = 3.0,
    skip_autofocus: bool = False,
) -> StageContext:
    cam, mnt, slv, stk, sto, foc = _default_mocks(camera, mount, solver, stacker, storage, focuser)

    def _noop_transition(log: SessionLog, state: SessionState) -> None:
        log.state = state

    return StageContext(
        camera=cam,
        mount=mnt,
        solver=slv,
        stacker=stk,
        storage=sto,
        focuser=foc,
        profile=optical_profile,
        stop_event=stop_event if stop_event is not None else threading.Event(),
        on_transition=on_transition if on_transition is not None else _noop_transition,
        target_ra=target_ra,
        target_dec=target_dec,
        stack_exposure_s=stack_exposure_s,
        stack_depth=stack_depth,
        preview_exposure_s=preview_exposure_s,
        preview_frames=preview_frames,
        autofocus_range_steps=autofocus_range_steps,
        autofocus_step_size=autofocus_step_size,
        autofocus_exposure_s=autofocus_exposure_s,
        skip_autofocus=skip_autofocus,
    )
