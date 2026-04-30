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
from .. import config as _cfg
from ..domain.frame_quality import FrameQualityConfig, FrameQualityFilter
from ..domain.refocus import RefocusConfig, RefocusTracker
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
    WIDE_FIELD_SEARCH_RADIUS_DEG as WIDE_FIELD_SEARCH_RADIUS_DEG,
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
    stage_autofocus,
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
        target_name: str = "M42",
        target_ra: float = M42_RA,
        target_dec: float = M42_DEC,
        stack_exposure_s: float = 30.0,
        stack_depth: int = 10,
        preview_exposure_s: float = 5.0,
        preview_frames: int = 3,
        autofocus_range_steps: int = 200,
        autofocus_step_size: int = 20,
        autofocus_exposure_s: float = 3.0,
        autofocus_backlash_steps: int = 0,
        skip_autofocus: bool = False,
        enable_refocus_triggers: bool = True,
        refocus_temp_delta_c: float = 1.0,
        refocus_alt_delta_deg: float = 5.0,
        refocus_elapsed_min: float = 30.0,
        enable_frame_quality: bool = True,
        frame_quality_min_snr: float = 0.3,
        frame_quality_baseline_frames: int = 3,
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
        self._target_name = target_name
        self._target_ra = target_ra
        self._target_dec = target_dec
        self._stack_exposure_s = stack_exposure_s
        self._stack_depth = stack_depth
        self._preview_exposure_s = preview_exposure_s
        self._preview_frames = preview_frames
        self._autofocus_range_steps = autofocus_range_steps
        self._autofocus_step_size = autofocus_step_size
        self._autofocus_exposure_s = autofocus_exposure_s
        self._autofocus_backlash_steps = autofocus_backlash_steps
        self._skip_autofocus = skip_autofocus
        self._enable_refocus_triggers = enable_refocus_triggers
        self._refocus_config = RefocusConfig(
            temp_delta_c=refocus_temp_delta_c,
            altitude_delta_deg=refocus_alt_delta_deg,
            elapsed_min=refocus_elapsed_min,
        )
        self._enable_frame_quality = enable_frame_quality
        self._frame_quality_config = FrameQualityConfig(
            min_snr_factor=frame_quality_min_snr,
            baseline_frames=frame_quality_baseline_frames,
        )

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
            target_name=self._target_name,
            target_ra=self._target_ra,
            target_dec=self._target_dec,
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
            target_ra=self._target_ra,
            target_dec=self._target_dec,
            stack_exposure_s=self._stack_exposure_s,
            stack_depth=self._stack_depth,
            preview_exposure_s=self._preview_exposure_s,
            preview_frames=self._preview_frames,
            autofocus_range_steps=self._autofocus_range_steps,
            autofocus_step_size=self._autofocus_step_size,
            autofocus_exposure_s=self._autofocus_exposure_s,
            autofocus_backlash_steps=self._autofocus_backlash_steps,
            skip_autofocus=self._skip_autofocus,
            refocus_tracker=(
                RefocusTracker(self._refocus_config)
                if self._enable_refocus_triggers and not self._skip_autofocus
                else None
            ),
            frame_quality_filter=(
                FrameQualityFilter(self._frame_quality_config)
                if self._enable_frame_quality
                else None
            ),
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
            ("autofocus",        lambda log: stage_autofocus(ctx, log)),
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
