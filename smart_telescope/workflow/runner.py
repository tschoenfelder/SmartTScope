"""VerticalSliceRunner — orchestrates the 8-stage session pipeline.

Stage logic lives in stages.py.  This module owns:
  - session lifecycle (run / stop)
  - state transitions and logging
  - stage timestamps
  - error wrapping
"""

from __future__ import annotations

import logging
import threading
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from ..domain.session import SessionLog, StageTimestamp
from ..domain.states import SessionState
from ..ports.camera import CameraPort
from ..ports.focuser import FocuserPort
from ..ports.mount import MountPort
from ..ports.solver import SolverPort
from ..ports.stacker import StackerPort
from ..ports.storage import StoragePort
from ._types import (
    C8_BARLOW2X as C8_BARLOW2X,
)
from ._types import (
    C8_NATIVE as C8_NATIVE,
)
from ._types import (
    C8_REDUCER as C8_REDUCER,
)
from ._types import (
    M42_DEC as M42_DEC,
)
from ._types import (
    M42_RA as M42_RA,
)
from ._types import (
    SOLVE_MAX_ATTEMPTS as SOLVE_MAX_ATTEMPTS,
)
from ._types import (
    OpticalProfile as OpticalProfile,
)
from ._types import (
    StateCallback as StateCallback,
)
from ._types import (
    WorkflowError as WorkflowError,
)
from .stages import (
    StageContext,
    stage_align,
    stage_connect,
    stage_goto,
    stage_initialize_mount,
    stage_preview,
    stage_recenter,
    stage_save,
    stage_stack,
)

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(UTC)


class VerticalSliceRunner:
    def __init__(
        self,
        camera: CameraPort,
        mount: MountPort,
        solver: SolverPort,
        stacker: StackerPort,
        storage: StoragePort,
        focuser: FocuserPort,
        optical_profile: OpticalProfile = C8_NATIVE,
        on_state_change: StateCallback | None = None,
    ) -> None:
        self._camera = camera
        self._mount = mount
        self._solver = solver
        self._stacker = stacker
        self._storage = storage
        self._focuser = focuser
        self._profile = optical_profile
        self._on_state_change = on_state_change
        self._stop_event = threading.Event()
        self._current_log: SessionLog | None = None

    @property
    def current_log(self) -> SessionLog | None:
        return self._current_log

    def stop(self) -> None:
        self._stop_event.set()
        self._mount.stop()

    def run(self, session_id: str | None = None) -> SessionLog:
        self._stop_event.clear()
        log = SessionLog(
            session_id=session_id or str(uuid.uuid4()),
            target_name="M42",
            target_ra=M42_RA,
            target_dec=M42_DEC,
            optical_config=self._profile.name,
            started_at=_now(),
        )
        self._current_log = log
        self._transition(log, SessionState.IDLE)

        ctx = StageContext(
            camera=self._camera,
            mount=self._mount,
            solver=self._solver,
            stacker=self._stacker,
            storage=self._storage,
            focuser=self._focuser,
            profile=self._profile,
            stop_event=self._stop_event,
            on_transition=self._transition,
        )

        try:
            for stage_name, stage_fn in self._pipeline(ctx):
                try:
                    self._start_stage(log, stage_name)
                    stage_fn(log)
                    self._finish_stage(log, stage_name)
                except WorkflowError:
                    raise
                except Exception as exc:
                    raise WorkflowError(stage_name, str(exc)) from exc
        except WorkflowError as err:
            log.failure_stage = err.stage
            log.failure_reason = err.reason
            self._transition(log, SessionState.FAILED)
        finally:
            if log.completed_at is None:
                log.completed_at = _now()
            self._mount.disconnect()
            self._camera.disconnect()
            self._focuser.disconnect()

        return log

    # ── Pipeline ─────────────────────────────────────────────────────────────

    def _pipeline(
        self, ctx: StageContext
    ) -> list[tuple[str, Callable[[SessionLog], None]]]:
        return [
            ("connect",          lambda log: stage_connect(ctx, log)),
            ("initialize_mount", lambda log: stage_initialize_mount(ctx, log)),
            ("align",            lambda log: stage_align(ctx, log)),
            ("goto",             lambda log: stage_goto(ctx, log)),
            ("recenter",         lambda log: stage_recenter(ctx, log)),
            ("preview",          lambda log: stage_preview(ctx, log)),
            ("stack",            lambda log: stage_stack(ctx, log)),
            ("save",             lambda log: stage_save(ctx, log)),
        ]

    # ── Orchestration helpers ─────────────────────────────────────────────────

    def _transition(self, log: SessionLog, state: SessionState) -> None:
        log.state = state
        logger.info("session=%s state=%s", log.session_id, state.name)
        if self._on_state_change:
            self._on_state_change(state)

    def _start_stage(self, log: SessionLog, name: str) -> None:
        log.stage_timestamps.append(StageTimestamp(stage=name, started_at=_now()))

    def _finish_stage(self, log: SessionLog, name: str) -> None:
        for ts in reversed(log.stage_timestamps):
            if ts.stage == name and ts.completed_at is None:
                ts.completed_at = _now()
                return
