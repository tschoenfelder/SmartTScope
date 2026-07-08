"""ObservingService — orchestrates the top-level ObservingStateMachine (Phase 1).

This is the single stateful orchestrator behind the new guided "Observe"
screen. It owns the current ObservingPhase (the FSM in domain/observing_state.py
is itself stateless) and, on each Intent, dispatches to the *existing* engines
rather than reimplementing them:

  WAIT_HOME_CONFIRMATION -> services.mount_operations.home_sequence (driven here)
  POLAR_ALIGN      -> domain.polar_workflow.PolarAlignmentWorkflow (driven here)
  FOCUS_READYING   -> workflow.stages.stage_autofocus
  TARGET_ACQUIRE   -> workflow.stages.stage_align / stage_goto / stage_recenter
  GUIDE_READYING   -> services.guiding_service.GuidingService
  CAPTURE_ACTIVE   -> workflow.stages.stage_stack / stage_save
  SAFE_STOPPING    -> services.mount_operations.park_sequence

Guards are computed best-effort from the outcome of each engine call — this is
intentionally a Phase 1 skeleton. Deferred to docs/todo.md backlog: dawn/meridian
auto-stop (G7), a graceful stop that distinguishes recoverable sub-operations
(G8), and stricter fault classification (G9/G10).

Callers never touch adapters directly through this service — they pass a fresh
ObservingDeps snapshot (obtained via FastAPI Depends, same as every other API
module in this codebase) on every call, because adapters can be rebuilt by
RuntimeContext.reset_for_tests()/connect_devices() between calls.
"""

from __future__ import annotations

import contextlib
import logging
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from astropy import units as u
from astropy.coordinates import EarthLocation
from astropy.time import Time

from ..domain.observing_state import (
    Guards,
    Intent,
    ObservingInput,
    ObservingPhase,
    ObservingStateMachine,
)
from ..domain.polar_workflow import (
    PolarAlignmentWorkflow,
)
from ..domain.polar_workflow import (
    SolveResult as PolarSolveResult,
)
from ..domain.polar_workflow import (
    WorkflowInput as PolarWorkflowInput,
)
from ..domain.session import SessionLog
from ..domain.states import SessionState
from ..ports.camera import CameraPort
from ..ports.focuser import FocuserPort
from ..ports.mount import MountPort, MountState
from ..ports.solver import SolverPort
from ..ports.stacker import StackerPort
from ..ports.storage import StoragePort
from ..workflow._types import C8_NATIVE, M42_DEC, M42_RA, OpticalProfile, WorkflowError
from ..workflow.stages import (
    StageContext,
    stage_align,
    stage_autofocus,
    stage_goto,
    stage_recenter,
    stage_save,
    stage_stack,
)
from . import mount_operations
from .device_state import DeviceStateService
from .hardware_coordinator import HardwareCommandCoordinator

if TYPE_CHECKING:
    from .guiding_service import GuidingService

_log = logging.getLogger(__name__)


@dataclass
class ObservingDeps:
    """Fresh adapters/config for one call — supplied by the API layer via Depends."""

    camera: CameraPort
    mount: MountPort
    focuser: FocuserPort
    solver: SolverPort
    stacker: StackerPort
    storage: StoragePort
    coordinator: HardwareCommandCoordinator
    device_state: DeviceStateService
    guiding_service: GuidingService
    optical_profile: OpticalProfile = field(default_factory=lambda: C8_NATIVE)
    target_ra: float = M42_RA
    target_dec: float = M42_DEC
    guide_role_cameras: dict[str, CameraPort] = field(default_factory=dict)
    observer_lat: float = 50.336
    observer_lon: float = 8.533
    ha_east_limit_h: float = -5.5
    ha_west_limit_h: float = 0.333


def _current_lst(lon_deg: float) -> float:
    loc = EarthLocation(lat=0.0 * u.deg, lon=lon_deg * u.deg)
    return float(Time.now().sidereal_time("apparent", longitude=loc.lon).hour)


def _wait_not_slewing(mount: MountPort, stop: threading.Event, timeout_s: float = 120.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if stop.is_set():
            return False
        if mount.get_state() != MountState.SLEWING:
            return True
        time.sleep(1.0)
    return False


# ── phase -> suggested-next-action tables (REQ-UX-003) ────────────────────────

_START_ACTIONS: dict[ObservingPhase, tuple[Intent, str]] = {
    ObservingPhase.WAIT_CONTEXT_CONFIRMATION: (Intent.CONFIRM_CONTEXT, "Confirm time & location"),
    ObservingPhase.WAIT_HOME_CONFIRMATION: (Intent.START_HOME, "Confirm HOME position"),
    ObservingPhase.POLAR_ALIGN: (Intent.START_POLAR_ALIGN, "Start polar alignment"),
    ObservingPhase.FOCUS_READYING: (Intent.START_FOCUS, "Start focus run"),
    ObservingPhase.TARGET_ACQUIRE: (
        Intent.START_TARGET_ACQUIRE, "Slew, solve & center target",
    ),
    ObservingPhase.GUIDE_READYING: (Intent.START_GUIDING, "Start guiding"),
    ObservingPhase.CAPTURE_ACTIVE: (Intent.STOP_SAFELY, "Stop safely (park)"),
    ObservingPhase.PAUSED_SAFE: (Intent.RESUME, "Resume"),
    ObservingPhase.FAULT: (Intent.ACKNOWLEDGE_FAULT, "Acknowledge & retry"),
}

# phase -> (accept-intent, label, guard attribute) shown once the engine result is in
_ACCEPT_ACTIONS: dict[ObservingPhase, tuple[Intent, str, str]] = {
    ObservingPhase.WAIT_HOME_CONFIRMATION: (
        Intent.CONFIRM_HOME, "Accept — home confirmed", "g2_home_confirmed",
    ),
    ObservingPhase.POLAR_ALIGN: (
        Intent.ACCEPT_POLAR_ALIGN, "Accept alignment", "g3_polar_within_tolerance",
    ),
    ObservingPhase.FOCUS_READYING: (Intent.ACCEPT_FOCUS, "Accept focus", "g4_focus_sufficient"),
    ObservingPhase.TARGET_ACQUIRE: (Intent.ACCEPT_TARGET, "Accept target", "g5_target_centered"),
    ObservingPhase.GUIDE_READYING: (Intent.START_CAPTURE, "Start capture", "g6_guiding_ok"),
}

_STOPPABLE_PHASES = frozenset({
    ObservingPhase.POLAR_ALIGN, ObservingPhase.FOCUS_READYING,
    ObservingPhase.TARGET_ACQUIRE, ObservingPhase.GUIDE_READYING,
})

# Safe-park is available here too, but "Pause" isn't — nothing is actively
# running yet to pause. See domain/observing_state.py's direct STOP_SAFELY
# checks in _on_wait_context/_on_wait_home.
_STOP_ONLY_PHASES = frozenset({
    ObservingPhase.WAIT_CONTEXT_CONFIRMATION, ObservingPhase.WAIT_HOME_CONFIRMATION,
})


def _primary_action(phase: ObservingPhase, guards: Guards, busy: bool) -> dict[str, Any] | None:
    if busy:
        return {"intent": None, "label": "Working…", "enabled": False}
    if phase in _ACCEPT_ACTIONS:
        intent, label, guard_attr = _ACCEPT_ACTIONS[phase]
        if getattr(guards, guard_attr):
            return {"intent": intent.value, "label": label, "enabled": True}
    if phase in _START_ACTIONS:
        intent, label = _START_ACTIONS[phase]
        return {"intent": intent.value, "label": label, "enabled": True}
    if phase is ObservingPhase.SAFE_STOPPING:
        return {"intent": None, "label": "Stopping safely…", "enabled": False}
    if phase is ObservingPhase.PARKED_SAFE:
        return {"intent": None, "label": "Session complete — parked safe", "enabled": False}
    return None


def _secondary_actions(phase: ObservingPhase) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    if phase in _STOPPABLE_PHASES:
        actions.append({"intent": Intent.PAUSE.value, "label": "Pause"})
        actions.append({"intent": Intent.STOP_SAFELY.value, "label": "Stop safely (park)"})
    elif phase in _STOP_ONLY_PHASES:
        actions.append({"intent": Intent.STOP_SAFELY.value, "label": "Stop safely (park)"})
    if phase is ObservingPhase.GUIDE_READYING:
        actions.append({"intent": Intent.SKIP_GUIDING.value, "label": "Skip guiding"})
    if phase is ObservingPhase.PAUSED_SAFE:
        actions.append({"intent": Intent.STOP_SAFELY.value, "label": "Stop safely (park)"})
    if phase is ObservingPhase.FAULT:
        actions.append({"intent": Intent.ABORT_TO_PARK.value, "label": "Abort to safe park"})
    return actions


def _guards_dict(guards: Guards) -> dict[str, bool | None]:
    return asdict(guards)


def _readiness(phase: ObservingPhase, guards: Guards) -> str:
    if phase in (ObservingPhase.FAULT, ObservingPhase.BOOTSTRAP):
        return "NOT_READY"
    if phase in (ObservingPhase.CAPTURE_ACTIVE, ObservingPhase.PARKED_SAFE):
        return "READY"
    return "LIMITED_READY"


class ObservingService:
    """Owns the current ObservingPhase; ObservingStateMachine itself is stateless."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._fsm = ObservingStateMachine()
        self._phase = ObservingPhase.BOOTSTRAP
        self._guards = Guards()
        self._paused_from: ObservingPhase | None = None
        self._fault_from: ObservingPhase | None = None
        self._fault_message: str | None = None
        self._busy = False
        self._detail: dict[str, Any] = {}
        self._stop_event = threading.Event()
        self._log: SessionLog | None = None
        # BOOTSTRAP has no user gate — advance immediately.
        self._phase = self._fsm.next(ObservingInput(phase=self._phase))

    # ── public API ────────────────────────────────────────────────────────────

    def snapshot(self, deps: ObservingDeps | None = None) -> dict[str, Any]:
        if deps is not None:
            self._maybe_auto_advance(deps)
        with self._lock:
            phase, guards, busy, detail, fault_message = (
                self._phase, self._guards, self._busy, dict(self._detail), self._fault_message,
            )
        return {
            "phase": phase.value,
            "guards": _guards_dict(guards),
            "busy": busy,
            "detail": detail,
            "fault_message": fault_message,
            "primary_action": _primary_action(phase, guards, busy),
            "secondary_actions": _secondary_actions(phase),
            "readiness": _readiness(phase, guards),
        }

    def handle_intent(self, intent: Intent, deps: ObservingDeps) -> dict[str, Any]:
        with self._lock:
            phase, busy = self._phase, self._busy
        if busy and intent not in (Intent.PAUSE, Intent.STOP_SAFELY, Intent.ABORT_TO_PARK):
            return self.snapshot(deps)

        # Side effects resolved synchronously before the FSM sees the intent.
        if intent is Intent.CONFIRM_CONTEXT and phase is ObservingPhase.WAIT_CONTEXT_CONFIRMATION:
            self._confirm_context(deps)
        elif intent is Intent.SKIP_GUIDING and phase is ObservingPhase.GUIDE_READYING:
            with self._lock:
                self._guards = replace(self._guards, g6_guiding_ok=True)

        with self._lock:
            inp = ObservingInput(
                phase=self._phase, intent=intent, guards=self._guards,
                paused_from_phase=self._paused_from, fault_from_phase=self._fault_from,
            )
            new_phase = self._fsm.next(inp)
            was_capturing = self._phase is ObservingPhase.CAPTURE_ACTIVE
            entering_capture = new_phase is ObservingPhase.CAPTURE_ACTIVE and not was_capturing
            was_paused = self._phase is ObservingPhase.PAUSED_SAFE
            if new_phase is ObservingPhase.PAUSED_SAFE and not was_paused:
                self._paused_from = self._phase
            if new_phase is not ObservingPhase.SAFE_STOPPING:
                self._stop_event.clear()
            self._phase = new_phase

        if intent is Intent.STOP_SAFELY or intent is Intent.ABORT_TO_PARK:
            self._stop_event.set()

        if intent is Intent.START_HOME and phase is ObservingPhase.WAIT_HOME_CONFIRMATION:
            self._spawn(self._run_home, deps)
        elif intent is Intent.START_POLAR_ALIGN and phase is ObservingPhase.POLAR_ALIGN:
            self._spawn(self._run_polar_align, deps)
        elif intent is Intent.START_FOCUS and phase is ObservingPhase.FOCUS_READYING:
            self._spawn(self._run_focus, deps)
        elif intent is Intent.START_TARGET_ACQUIRE and phase is ObservingPhase.TARGET_ACQUIRE:
            self._spawn(self._run_target_acquire, deps)
        elif intent is Intent.START_GUIDING and phase is ObservingPhase.GUIDE_READYING:
            self._spawn(self._run_guiding, deps)
        elif entering_capture:
            self._spawn(self._run_capture, deps)

        return self.snapshot(deps)

    # ── auto-advance (safe-stop retries whenever the caller polls) ────────────

    def _maybe_auto_advance(self, deps: ObservingDeps) -> None:
        with self._lock:
            phase, busy = self._phase, self._busy
        if phase is not ObservingPhase.SAFE_STOPPING or busy:
            return
        # A previous _run_safe_stop attempt may have already set g8 True (or a
        # previous poll may have started one) — re-check the FSM with the
        # current guards before deciding whether another attempt is needed.
        with self._lock:
            new_phase = self._fsm.next(ObservingInput(phase=self._phase, guards=self._guards))
            self._phase = new_phase
        if new_phase is ObservingPhase.SAFE_STOPPING:
            self._spawn(self._run_safe_stop, deps)

    # ── synchronous confirmations ─────────────────────────────────────────────

    def _confirm_context(self, deps: ObservingDeps) -> None:
        try:
            deps.mount.ensure_time_location_synced()
            ok = True
        except Exception as exc:
            _log.warning("Context confirmation failed: %s", exc)
            ok = False
        with self._lock:
            self._guards = replace(self._guards, g1_context_confirmed=ok)

    # ── background engine work ────────────────────────────────────────────────

    def _spawn(self, fn: Callable[[ObservingDeps], None], deps: ObservingDeps) -> None:
        with self._lock:
            if self._busy:
                return
            self._busy = True
            fault_from_phase = self._phase

        def _run() -> None:
            try:
                fn(deps)
            except Exception as exc:
                _log.exception("Observing engine failure in phase %s", fault_from_phase)
                with self._lock:
                    self._fault_from = fault_from_phase
                    self._fault_message = str(exc)
                    self._guards = replace(
                        self._guards, g9_error_recoverable=True, g10_error_unrecoverable=False,
                    )
                    self._phase = ObservingPhase.FAULT
            finally:
                with self._lock:
                    self._busy = False

        threading.Thread(target=_run, daemon=True, name="observing-worker").start()

    def _stage_context(self, deps: ObservingDeps) -> tuple[StageContext, SessionLog]:
        if self._log is None:
            with self._lock:
                if self._log is None:
                    self._log = SessionLog(
                        session_id=str(uuid.uuid4()),
                        target_name="observing-session",
                        target_ra=deps.target_ra,
                        target_dec=deps.target_dec,
                        optical_config=deps.optical_profile.name,
                        started_at=datetime.now(UTC),
                    )
        ctx = StageContext(
            camera=deps.camera, mount=deps.mount, solver=deps.solver, stacker=deps.stacker,
            storage=deps.storage, focuser=deps.focuser, profile=deps.optical_profile,
            stop_event=self._stop_event, on_transition=self._on_transition,
            target_ra=deps.target_ra, target_dec=deps.target_dec,
        )
        return ctx, self._log

    def _on_transition(self, log: SessionLog, state: SessionState) -> None:
        with self._lock:
            self._detail["session_state"] = state.name

    def _run_home(self, deps: ObservingDeps) -> None:
        mount_operations.home_sequence(deps.mount, deps.coordinator)
        state = deps.mount.get_state()
        with self._lock:
            self._detail["home"] = {"mount_state": state.name}
            self._guards = replace(self._guards, g2_home_confirmed=state is MountState.AT_HOME)

    def _run_polar_align(self, deps: ObservingDeps) -> None:
        wf = PolarAlignmentWorkflow(
            observer_lat=deps.observer_lat, observer_lon=deps.observer_lon,
            ha_east_limit_h=deps.ha_east_limit_h, ha_west_limit_h=deps.ha_west_limit_h,
        )
        inp = PolarWorkflowInput(
            lst=_current_lst(deps.observer_lon), observer_lat=deps.observer_lat,
        )
        while True:
            if self._stop_event.is_set():
                with self._lock:
                    self._detail["polar_align"] = {"message": "Stopped by request"}
                return
            act = wf.next_action(inp)
            if act.kind == "SLEW_TO_RA":
                assert act.ra_h is not None
                ok = deps.mount.goto(act.ra_h, act.dec_deg)
                if ok:
                    ok = _wait_not_slewing(deps.mount, self._stop_event)
                inp = PolarWorkflowInput(
                    slew_ok=ok, lst=_current_lst(deps.observer_lon), observer_lat=deps.observer_lat,
                )
            elif act.kind == "CAPTURE_AND_SOLVE":
                frame = deps.camera.capture(5.0)
                r = deps.solver.solve(frame, deps.optical_profile.pixel_scale_arcsec)
                solve_result = PolarSolveResult(
                    success=r.success, ra=r.ra, dec=r.dec, error=r.error or "",
                )
                inp = PolarWorkflowInput(
                    solve_result=solve_result,
                    lst=_current_lst(deps.observer_lon), observer_lat=deps.observer_lat,
                )
            elif act.kind == "DISPLAY_RESULT":
                assert act.result is not None
                with self._lock:
                    self._detail["polar_align"] = asdict(act.result)
                    self._guards = replace(
                        self._guards, g3_polar_within_tolerance=act.result.target_reached,
                    )
                return
            else:  # COARSE_REQUIRED or FAILED
                with self._lock:
                    self._detail["polar_align"] = {"message": act.message}
                    self._guards = replace(self._guards, g3_polar_within_tolerance=False)
                return

    def _run_focus(self, deps: ObservingDeps) -> None:
        ctx, log = self._stage_context(deps)
        stage_autofocus(ctx, log)
        with self._lock:
            self._detail["focus"] = {
                "best_position": log.autofocus_best_position,
                "metric_gain": log.autofocus_metric_gain,
            }
            self._guards = replace(self._guards, g4_focus_sufficient=True)

    def _run_target_acquire(self, deps: ObservingDeps) -> None:
        ctx, log = self._stage_context(deps)
        stage_align(ctx, log)
        stage_goto(ctx, log)
        stage_recenter(ctx, log)
        with self._lock:
            self._detail["target_acquire"] = {
                "centering_state": log.centering_state,
                "centering_offset_arcmin": log.centering_offset_arcmin,
                "centering_iterations": log.centering_iterations,
            }
            self._guards = replace(
                self._guards,
                g5_target_centered=log.centering_state in ("CENTERED", "CENTERING_DEGRADED"),
            )

    def _run_guiding(self, deps: ObservingDeps) -> None:
        if not deps.guide_role_cameras:
            with self._lock:
                self._guards = replace(self._guards, g6_guiding_ok=True)
            return
        deps.guiding_service.start(deps.guide_role_cameras, mount=deps.mount)
        time.sleep(2.0)  # let the measurement loop collect a few frames
        status = deps.guiding_service.status()
        ok = status.state == "running" and status.active_role is not None
        with self._lock:
            self._detail["guiding"] = status.to_dict()
            self._guards = replace(self._guards, g6_guiding_ok=ok)

    def _run_capture(self, deps: ObservingDeps) -> None:
        ctx, log = self._stage_context(deps)
        try:
            stage_stack(ctx, log)
        except WorkflowError as exc:
            if exc.stage == "stack" and "cancelled" in exc.reason.lower():
                _log.info("Capture loop stopped by request")
            else:
                raise
        with self._lock:
            self._detail["capture"] = {
                "frames_integrated": log.frames_integrated,
                "frames_rejected": log.frames_rejected,
            }
        if not self._stop_event.is_set():
            stage_save(ctx, log)
            with self._lock:
                self._detail["capture"]["saved_image_path"] = log.saved_image_path

    def _run_safe_stop(self, deps: ObservingDeps) -> None:
        if deps.guide_role_cameras:
            with contextlib.suppress(Exception):
                deps.guiding_service.stop()
        mount_operations.park_sequence(deps.mount, deps.coordinator, deps.device_state)
        deps.device_state.poll_now()
        obs = deps.device_state.get_mount_state()
        parked = obs is not None and obs.state == MountState.PARKED
        with self._lock:
            self._guards = replace(self._guards, g8_safe_stop_possible=parked)
