"""
Shared fixtures for unit tests.

All port fixtures return Mock(spec=<Port>) pre-configured for the happy path.
Individual tests override specific attributes for the scenario under test.
Hand-rolled fakes (MockCamera, MockMount, …) stay in tests/integration/ — they
are not used in unit tests.
"""
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from smart_telescope.domain.session import SessionLog
from smart_telescope.domain.states import SessionState
from smart_telescope.ports.camera import CameraPort, Frame
from smart_telescope.ports.mount import MountPort, MountPosition, MountState
from smart_telescope.ports.solver import SolverPort, SolveResult
from smart_telescope.ports.stacker import StackerPort, StackedImage
from smart_telescope.ports.storage import StoragePort
from smart_telescope.workflow.runner import (
    C8_NATIVE,
    M42_DEC,
    M42_RA,
    VerticalSliceRunner,
)


# ── Primitive builders ─────────────────────────────────────────────────────


def make_frame(exposure: float = 5.0) -> Frame:
    return Frame(data=b"FAKE_FITS", width=3096, height=2080, exposure_seconds=exposure)


def make_stacked(n: int = 1) -> StackedImage:
    return StackedImage(data=b"FAKE_STACK", frames_integrated=n, frames_rejected=0)


def make_log() -> SessionLog:
    return SessionLog(
        session_id="test-session-001",
        target_name="M42",
        target_ra=M42_RA,
        target_dec=M42_DEC,
        optical_config=C8_NATIVE.name,
        started_at=datetime(2026, 4, 21, 21, 0, 0, tzinfo=timezone.utc),
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
    mnt.get_state.return_value = MountState.PARKED
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


# ── Runner factory ─────────────────────────────────────────────────────────


def make_unit_runner(
    camera: Mock | None = None,
    mount: Mock | None = None,
    solver: Mock | None = None,
    stacker: Mock | None = None,
    storage: Mock | None = None,
    optical_profile=C8_NATIVE,
) -> VerticalSliceRunner:
    """
    Create a VerticalSliceRunner with fresh happy-path mocks for every port
    not explicitly supplied. Use this in unit tests that call stage methods
    directly rather than runner.run().
    """
    return VerticalSliceRunner(
        camera=camera if camera is not None else Mock(spec=CameraPort, **{
            "connect.return_value": True,
            "capture.return_value": make_frame(),
        }),
        mount=mount if mount is not None else Mock(spec=MountPort, **{
            "connect.return_value": True,
            "get_state.return_value": MountState.PARKED,
            "unpark.return_value": True,
            "enable_tracking.return_value": True,
            "sync.return_value": True,
            "goto.return_value": True,
            "is_slewing.return_value": False,
            "get_position.return_value": MountPosition(ra=M42_RA, dec=M42_DEC),
        }),
        solver=solver if solver is not None else Mock(spec=SolverPort, **{
            "solve.return_value": SolveResult(success=True, ra=M42_RA, dec=M42_DEC),
        }),
        stacker=stacker if stacker is not None else Mock(spec=StackerPort, **{
            "add_frame.return_value": make_stacked(1),
            "get_current_stack.return_value": make_stacked(10),
        }),
        storage=storage if storage is not None else Mock(spec=StoragePort, **{
            "has_free_space.return_value": True,
            "save_image.return_value": "/data/result.png",
            "save_log.return_value": "/data/log.json",
        }),
        optical_profile=optical_profile,
    )
