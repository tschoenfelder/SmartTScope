"""Unit tests for ObservingService — the orchestrator behind the ObservingStateMachine.

Uses the same Mock(spec=Port) fixtures as tests/unit/workflow/test_runner_stages.py
(camera_mock, mount_mock, solver_mock, stacker_mock, storage_mock, focuser_mock from
tests/conftest.py) so each engine call (stage_autofocus, stage_align/goto/recenter,
stage_stack, PolarAlignmentWorkflow, mount_operations.park_sequence) runs against
mocked hardware exactly like the existing stage-function tests.
"""

from __future__ import annotations

import time
from dataclasses import replace
from unittest.mock import Mock

import pytest

from smart_telescope.domain.observing_state import Intent, ObservingPhase
from smart_telescope.ports.mount import MountState
from smart_telescope.ports.solver import SolveResult
from smart_telescope.services.device_state import DeviceStateService, MountObservedState
from smart_telescope.services.hardware_coordinator import HardwareCommandCoordinator
from smart_telescope.services.observing_service import ObservingDeps, ObservingService
from smart_telescope.workflow.runner import C8_NATIVE, M42_DEC, M42_RA

P = ObservingPhase
IT = Intent


def _wait_idle(svc: ObservingService, deps: ObservingDeps, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    snap = svc.snapshot(deps)
    while snap["busy"]:
        if time.monotonic() > deadline:
            raise TimeoutError(f"ObservingService did not finish; last detail={snap['detail']}")
        time.sleep(0.02)
        snap = svc.snapshot(deps)
    return snap


def _device_state(observed_state: MountState | None = None) -> DeviceStateService:
    """Real DeviceStateService (no background thread since .start() is never called);
    poll_now()/poll_until_changed() are no-ops against `_mount is None`, so the
    manually-seeded cache below is what mount_operations reads back."""
    svc = DeviceStateService()
    if observed_state is not None:
        with svc._lock:
            svc._mount_state = MountObservedState(
                state=observed_state, ra=None, dec=None, polled_at=time.monotonic(),
            )
    return svc


def _deps(
    camera_mock, mount_mock, solver_mock, stacker_mock, storage_mock, focuser_mock,
    guide_role_cameras: dict | None = None,
) -> ObservingDeps:
    return ObservingDeps(
        camera=camera_mock,
        mount=mount_mock,
        focuser=focuser_mock,
        solver=solver_mock,
        stacker=stacker_mock,
        storage=storage_mock,
        coordinator=HardwareCommandCoordinator(),
        device_state=_device_state(),
        guiding_service=Mock(),
        optical_profile=C8_NATIVE,
        target_ra=M42_RA,
        target_dec=M42_DEC,
        guide_role_cameras=guide_role_cameras or {},
        observer_lat=50.0,
        observer_lon=8.5,
        ha_east_limit_h=-12.0,
        ha_west_limit_h=12.0,
    )


@pytest.fixture()
def deps(
    camera_mock, mount_mock, solver_mock, stacker_mock, storage_mock, focuser_mock,
) -> ObservingDeps:
    return _deps(camera_mock, mount_mock, solver_mock, stacker_mock, storage_mock, focuser_mock)


class TestBootstrap:
    def test_advances_past_bootstrap_on_construction(self) -> None:
        svc = ObservingService()
        assert svc.snapshot()["phase"] == P.WAIT_CONTEXT_CONFIRMATION.value


class TestConfirmContext:
    def test_success_advances_to_wait_home_confirmation(self, deps: ObservingDeps) -> None:
        svc = ObservingService()
        snap = svc.handle_intent(IT.CONFIRM_CONTEXT, deps)
        assert snap["phase"] == P.WAIT_HOME_CONFIRMATION.value
        assert snap["guards"]["g1_context_confirmed"] is True
        deps.mount.ensure_time_location_synced.assert_called_once()

    def test_hardware_failure_keeps_phase_and_guard_false(self, deps: ObservingDeps) -> None:
        deps.mount.ensure_time_location_synced.side_effect = RuntimeError("clock not trusted")
        svc = ObservingService()
        snap = svc.handle_intent(IT.CONFIRM_CONTEXT, deps)
        assert snap["phase"] == P.WAIT_CONTEXT_CONFIRMATION.value
        assert snap["guards"]["g1_context_confirmed"] is False


class TestConfirmHome:
    def test_start_home_runs_sequence_and_accept_advances(self, deps: ObservingDeps) -> None:
        svc = ObservingService()
        svc.handle_intent(IT.CONFIRM_CONTEXT, deps)
        deps.mount.get_state.return_value = MountState.AT_HOME

        svc.handle_intent(IT.START_HOME, deps)
        snap = _wait_idle(svc, deps)
        assert snap["phase"] == P.WAIT_HOME_CONFIRMATION.value  # accept not sent yet
        assert snap["guards"]["g2_home_confirmed"] is True
        assert snap["detail"]["home"] == {"mount_state": "AT_HOME"}
        deps.mount.go_home.assert_called_once()
        # Setting the park position must never be automatic here — see
        # wiki/log.md 2026-06-14 "CRITICAL: remove auto_set_park": it silently
        # overwrites the user's deliberately configured EEPROM park position.
        deps.mount.set_park_position.assert_not_called()

        snap = svc.handle_intent(IT.CONFIRM_HOME, deps)
        assert snap["phase"] == P.POLAR_ALIGN.value

    def test_home_not_reached_keeps_guard_false_and_allows_retry(self, deps: ObservingDeps) -> None:
        svc = ObservingService()
        svc.handle_intent(IT.CONFIRM_CONTEXT, deps)
        deps.mount.get_state.return_value = MountState.TRACKING  # never reaches AT_HOME

        svc.handle_intent(IT.START_HOME, deps)
        snap = _wait_idle(svc, deps)
        assert snap["phase"] == P.WAIT_HOME_CONFIRMATION.value
        assert snap["guards"]["g2_home_confirmed"] is False
        assert snap["primary_action"]["intent"] == IT.START_HOME.value  # offered again, not Accept

        snap = svc.handle_intent(IT.CONFIRM_HOME, deps)  # accept refused — guard still false
        assert snap["phase"] == P.WAIT_HOME_CONFIRMATION.value

    def test_hardware_failure_faults(self, deps: ObservingDeps) -> None:
        svc = ObservingService()
        svc.handle_intent(IT.CONFIRM_CONTEXT, deps)
        deps.mount.get_state.return_value = MountState.PARKED
        deps.mount.unpark.return_value = False

        svc.handle_intent(IT.START_HOME, deps)
        snap = _wait_idle(svc, deps)
        assert snap["phase"] == P.FAULT.value
        assert "Auto-unpark before home failed" in snap["fault_message"]


def _advance_to(svc: ObservingService, deps: ObservingDeps, phase: ObservingPhase) -> None:
    """Drive the FSM up to (but not past) `phase` using the happy path."""
    deps.mount.get_state.return_value = MountState.AT_HOME  # so _run_home's guard check succeeds
    order = [
        (P.WAIT_HOME_CONFIRMATION, IT.CONFIRM_CONTEXT),
        (P.WAIT_HOME_CONFIRMATION, IT.START_HOME),
        (P.POLAR_ALIGN, IT.CONFIRM_HOME),
    ]
    for _target, intent in order:
        if svc.snapshot(deps)["phase"] == phase.value:
            return
        svc.handle_intent(intent, deps)
        _wait_idle(svc, deps)
        if svc.snapshot(deps)["phase"] == phase.value:
            return


class TestPolarAlign:
    def test_start_runs_workflow_and_populates_guard(self, deps: ObservingDeps) -> None:
        _advance_to(svc := ObservingService(), deps, P.POLAR_ALIGN)
        assert svc.snapshot(deps)["phase"] == P.POLAR_ALIGN.value

        deps.solver.solve.side_effect = [
            SolveResult(success=True, ra=11.0, dec=89.5),
            SolveResult(success=True, ra=12.0, dec=89.4),
            SolveResult(success=True, ra=13.0, dec=89.6),
        ]
        svc.handle_intent(IT.START_POLAR_ALIGN, deps)
        snap = _wait_idle(svc, deps)

        assert snap["phase"] == P.POLAR_ALIGN.value  # ACCEPT not sent yet
        assert snap["guards"]["g3_polar_within_tolerance"] in (True, False)
        assert "polar_align" in snap["detail"]

    def test_solve_failure_sets_guard_false_without_fault(self, deps: ObservingDeps) -> None:
        _advance_to(svc := ObservingService(), deps, P.POLAR_ALIGN)
        deps.solver.solve.return_value = SolveResult(success=False, error="no stars")
        svc.handle_intent(IT.START_POLAR_ALIGN, deps)
        snap = _wait_idle(svc, deps)
        assert snap["phase"] == P.POLAR_ALIGN.value
        assert snap["guards"]["g3_polar_within_tolerance"] is False

    def test_accept_requires_guard(self, deps: ObservingDeps) -> None:
        _advance_to(svc := ObservingService(), deps, P.POLAR_ALIGN)
        deps.solver.solve.side_effect = [
            SolveResult(success=True, ra=11.0, dec=89.5),
            SolveResult(success=True, ra=12.0, dec=89.4),
            SolveResult(success=True, ra=13.0, dec=89.6),
        ]
        svc.handle_intent(IT.START_POLAR_ALIGN, deps)
        _wait_idle(svc, deps)
        snap = svc.handle_intent(IT.ACCEPT_POLAR_ALIGN, deps)
        reached = snap["guards"]["g3_polar_within_tolerance"]
        expected = P.FOCUS_READYING.value if reached else P.POLAR_ALIGN.value
        assert snap["phase"] == expected


class TestFocusReadying:
    def test_start_runs_autofocus_and_sets_guard(self, deps: ObservingDeps) -> None:
        svc = ObservingService()
        svc._phase = P.FOCUS_READYING  # polar-align wiring covered by TestPolarAlign

        svc.handle_intent(IT.START_FOCUS, deps)
        snap = _wait_idle(svc, deps)
        assert snap["phase"] == P.FOCUS_READYING.value
        assert snap["guards"]["g4_focus_sufficient"] is True
        assert "focus" in snap["detail"]


class TestGuideReadying:
    def test_skip_guiding_sets_guard_without_starting_service(self, deps: ObservingDeps) -> None:
        svc = ObservingService()
        svc._phase = P.GUIDE_READYING  # jump directly — earlier phases covered above
        snap = svc.handle_intent(IT.SKIP_GUIDING, deps)
        assert snap["guards"]["g6_guiding_ok"] is True
        deps.guiding_service.start.assert_not_called()

    def test_start_guiding_with_no_role_cameras_sets_guard_true(self, deps: ObservingDeps) -> None:
        svc = ObservingService()
        svc._phase = P.GUIDE_READYING
        svc.handle_intent(IT.START_GUIDING, deps)
        snap = _wait_idle(svc, deps)
        assert snap["guards"]["g6_guiding_ok"] is True
        deps.guiding_service.start.assert_not_called()

    def test_start_guiding_with_role_cameras_polls_status(
        self, deps: ObservingDeps, camera_mock,
    ) -> None:
        deps.guide_role_cameras = {"guide": camera_mock}
        status = Mock()
        status.state = "running"
        status.active_role = "guide"
        status.to_dict.return_value = {"state": "running"}
        deps.guiding_service.status.return_value = status

        svc = ObservingService()
        svc._phase = P.GUIDE_READYING
        svc.handle_intent(IT.START_GUIDING, deps)
        snap = _wait_idle(svc, deps, timeout=10.0)
        deps.guiding_service.start.assert_called_once()
        assert snap["guards"]["g6_guiding_ok"] is True


class TestCaptureActiveAutoStart:
    def test_entering_capture_active_starts_stack_and_populates_detail(
        self, deps: ObservingDeps, stacker_mock,
    ) -> None:
        svc = ObservingService()
        svc._phase = P.GUIDE_READYING
        svc._guards = svc._guards.__class__(g6_guiding_ok=True)
        snap = svc.handle_intent(IT.START_CAPTURE, deps)
        assert snap["phase"] == P.CAPTURE_ACTIVE.value
        snap = _wait_idle(svc, deps, timeout=10.0)
        assert "capture" in snap["detail"]
        stacker_mock.add_frame.assert_called()


class TestSafeStopping:
    def test_stop_safely_parks_mount_and_sets_guard(self, deps: ObservingDeps) -> None:
        svc = ObservingService()
        svc._phase = P.CAPTURE_ACTIVE
        deps.mount.get_state.return_value = MountState.TRACKING
        # Pre-seed the cache as already PARKED — poll_now()/poll_until_changed()
        # no-op against a DeviceStateService that was never .start()-ed, so this
        # is what park_sequence's "did it change?" poll and _run_safe_stop's
        # final check both read back (see _device_state() docstring above).
        deps.device_state = _device_state(MountState.PARKED)

        snap = svc.handle_intent(IT.STOP_SAFELY, deps)
        assert snap["phase"] == P.SAFE_STOPPING.value
        snap = _wait_idle(svc, deps, timeout=10.0)
        assert snap["phase"] == P.PARKED_SAFE.value
        assert snap["guards"]["g8_safe_stop_possible"] is True

    def test_stop_safely_stays_in_safe_stopping_when_still_slewing(
        self, deps: ObservingDeps,
    ) -> None:
        """Park command accepted but mount hasn't reached PARKED yet — retry, don't fault."""
        svc = ObservingService()
        svc._phase = P.CAPTURE_ACTIVE
        deps.mount.get_state.return_value = MountState.TRACKING
        deps.mount.park.return_value = True
        deps.device_state = _device_state(MountState.SLEWING)

        snap = svc.handle_intent(IT.STOP_SAFELY, deps)
        snap = _wait_idle(svc, deps, timeout=10.0)
        assert snap["phase"] == P.SAFE_STOPPING.value
        assert snap["guards"]["g8_safe_stop_possible"] is False

    def test_stop_safely_does_not_resend_park_command_on_retry(
        self, deps: ObservingDeps,
    ) -> None:
        """Regression test (real-hardware report 2026-07-08): _maybe_auto_advance()
        re-spawns _run_safe_stop() on every poll while SAFE_STOPPING hasn't reached
        PARKED yet. :hP# is fire-and-forget and its slew can take up to 120 s;
        blindly resending it on each retry was observed on real hardware to get a
        second :hP# rejected by OnStep while the first (accepted) one was still
        resolving. mount.park() must be called at most once across repeated
        auto-advance retries while device_state hasn't reached PARKED."""
        svc = ObservingService()
        svc._phase = P.CAPTURE_ACTIVE
        deps.mount.get_state.return_value = MountState.TRACKING
        deps.mount.park.return_value = True
        deps.device_state = _device_state(MountState.SLEWING)  # never reaches PARKED

        snap = svc.handle_intent(IT.STOP_SAFELY, deps)
        snap = _wait_idle(svc, deps, timeout=10.0)
        assert snap["phase"] == P.SAFE_STOPPING.value
        assert deps.mount.park.call_count == 1

        # Simulate further polls (observing.js polls every 2.5 s) — each one
        # runs _maybe_auto_advance() again since g8 is still False.
        for _ in range(3):
            snap = _wait_idle(svc, deps, timeout=10.0)
        assert snap["phase"] == P.SAFE_STOPPING.value
        assert deps.mount.park.call_count == 1


class TestSafeParkFromWaitPhases:
    """Safe-park must be reachable even before anything is "active" (REQ:
    user report 2026-07-08 — the always-visible Stop button only halts, it
    doesn't park; before this fix the graceful park path was unavailable
    during WAIT_CONTEXT_CONFIRMATION/WAIT_HOME_CONFIRMATION)."""

    def test_wait_context_offers_stop_only_not_pause(self, deps: ObservingDeps) -> None:
        svc = ObservingService()
        snap = svc.snapshot(deps)
        assert snap["phase"] == P.WAIT_CONTEXT_CONFIRMATION.value
        intents = {a["intent"] for a in snap["secondary_actions"]}
        assert intents == {IT.STOP_SAFELY.value}

    def test_wait_context_stop_safely_reaches_parked_safe(self, deps: ObservingDeps) -> None:
        svc = ObservingService()
        deps.device_state = _device_state(MountState.PARKED)
        snap = svc.handle_intent(IT.STOP_SAFELY, deps)
        assert snap["phase"] == P.SAFE_STOPPING.value
        snap = _wait_idle(svc, deps, timeout=10.0)
        assert snap["phase"] == P.PARKED_SAFE.value
        assert snap["guards"]["g8_safe_stop_possible"] is True

    def test_wait_home_offers_stop_only_not_pause(self, deps: ObservingDeps) -> None:
        svc = ObservingService()
        svc._phase = P.WAIT_HOME_CONFIRMATION
        snap = svc.snapshot(deps)
        intents = {a["intent"] for a in snap["secondary_actions"]}
        assert intents == {IT.STOP_SAFELY.value}

    def test_wait_home_stop_safely_reaches_parked_safe(self, deps: ObservingDeps) -> None:
        svc = ObservingService()
        svc._phase = P.WAIT_HOME_CONFIRMATION
        deps.device_state = _device_state(MountState.PARKED)
        snap = svc.handle_intent(IT.STOP_SAFELY, deps)
        assert snap["phase"] == P.SAFE_STOPPING.value
        snap = _wait_idle(svc, deps, timeout=10.0)
        assert snap["phase"] == P.PARKED_SAFE.value
        assert snap["guards"]["g8_safe_stop_possible"] is True


class TestSafeStoppingRecovery:
    """M9-034: after a manual STOP mid-park-slew the mount is neither parked
    nor moving — SAFE_STOPPING must offer a way out (hardware report
    2026-07-17): explicit park retry (bypasses the M9-027 no-resend window)
    and a route back to the homing step."""

    def _stuck_safe_stop(self, svc: ObservingService, deps: ObservingDeps) -> dict:
        svc._phase = P.WAIT_HOME_CONFIRMATION
        deps.mount.get_state.return_value = MountState.TRACKING
        deps.mount.park.return_value = True
        deps.device_state = _device_state(MountState.SLEWING)  # never reaches PARKED
        svc.handle_intent(IT.STOP_SAFELY, deps)
        snap = _wait_idle(svc, deps, timeout=10.0)
        assert snap["phase"] == P.SAFE_STOPPING.value
        assert deps.mount.park.call_count == 1
        return snap

    def test_safe_stopping_offers_retry_and_back_to_homing(self, deps: ObservingDeps) -> None:
        svc = ObservingService()
        snap = self._stuck_safe_stop(svc, deps)
        intents = {a["intent"] for a in snap["secondary_actions"]}
        assert intents == {IT.STOP_SAFELY.value, IT.UNPARK_CONTINUE.value}

    def test_explicit_retry_bypasses_no_resend_window(self, deps: ObservingDeps) -> None:
        svc = ObservingService()
        self._stuck_safe_stop(svc, deps)
        svc.handle_intent(IT.STOP_SAFELY, deps)  # "Retry park now"
        snap = _wait_idle(svc, deps, timeout=10.0)
        assert deps.mount.park.call_count == 2
        assert snap["phase"] == P.SAFE_STOPPING.value  # mock still never parks

    def test_back_to_homing_returns_to_wait_home(self, deps: ObservingDeps) -> None:
        svc = ObservingService()
        self._stuck_safe_stop(svc, deps)
        snap = svc.handle_intent(IT.UNPARK_CONTINUE, deps)
        assert snap["phase"] == P.WAIT_HOME_CONFIRMATION.value
        assert snap["guards"]["g8_safe_stop_possible"] is False
        assert snap["primary_action"]["intent"] == IT.START_HOME.value

    def test_unpark_continue_passes_busy_gate(self, deps: ObservingDeps) -> None:
        # M9-034 reopened (Pi 2026-07-17): _maybe_auto_advance keeps a worker
        # in flight during most UI polls, so a busy-gated UNPARK_CONTINUE was
        # silently dropped — the escape hatch must work while busy.
        svc = ObservingService()
        self._stuck_safe_stop(svc, deps)
        with svc._lock:
            svc._busy = True  # simulate a worker still in flight
        snap = svc.handle_intent(IT.UNPARK_CONTINUE, deps)
        assert snap["phase"] == P.WAIT_HOME_CONFIRMATION.value

    def test_late_safe_stop_worker_does_not_clobber_escape(self, deps: ObservingDeps) -> None:
        # A worker finishing AFTER the user escaped must not write g8=True
        # into WAIT_HOME_CONFIRMATION (would fast-forward the next safe-stop).
        svc = ObservingService()
        svc._phase = P.WAIT_HOME_CONFIRMATION
        deps = replace(deps, device_state=_device_state(MountState.PARKED))
        svc._run_safe_stop(deps)  # simulate the late worker body directly
        snap = svc.snapshot()
        assert snap["guards"]["g8_safe_stop_possible"] is not True
        assert "safe_stop" not in snap["detail"]

    def test_detail_reflects_current_action_not_previous(self, deps: ObservingDeps) -> None:
        # M9-034: the stale home record (home: AT_HOME) kept showing in the
        # Detail panel during/after a park, reading as a wrong live status.
        svc = ObservingService()
        svc.handle_intent(IT.CONFIRM_CONTEXT, deps)
        deps.mount.get_state.return_value = MountState.AT_HOME
        svc.handle_intent(IT.START_HOME, deps)
        snap = _wait_idle(svc, deps)
        assert "home" in snap["detail"]

        deps.mount.get_state.return_value = MountState.TRACKING
        deps2 = replace(deps, device_state=_device_state(MountState.PARKED))
        svc.handle_intent(IT.STOP_SAFELY, deps2)
        snap = _wait_idle(svc, deps2, timeout=10.0)
        assert "home" not in snap["detail"]
        assert snap["detail"]["safe_stop"]["parked"] is True


class TestEmergencyStopHaltsParkRetries:
    """M9-035: the hardware emergency stop must halt SAFE_STOPPING's automatic
    park retries — hardware evidence 2026-07-17 showed the app would have
    re-issued :hP# ~120 s after the user emergency-stopped the park slew."""

    def _stuck_safe_stop(self, svc: ObservingService, deps: ObservingDeps) -> None:
        svc._phase = P.WAIT_HOME_CONFIRMATION
        deps.mount.get_state.return_value = MountState.TRACKING
        deps.mount.park.return_value = True
        deps.device_state = _device_state(MountState.SLEWING)  # never reaches PARKED
        svc.handle_intent(IT.STOP_SAFELY, deps)
        snap = _wait_idle(svc, deps, timeout=10.0)
        assert snap["phase"] == P.SAFE_STOPPING.value
        assert deps.mount.park.call_count == 1

    def test_moves_safe_stopping_to_paused_and_clears_window(
        self, deps: ObservingDeps,
    ) -> None:
        svc = ObservingService()
        self._stuck_safe_stop(svc, deps)
        svc.on_emergency_stop()
        snap = svc.snapshot()
        assert snap["phase"] == P.PAUSED_SAFE.value
        with svc._lock:
            assert svc._park_command_issued_at is None

    def test_resume_reenters_safe_stopping_and_reissues_park(
        self, deps: ObservingDeps,
    ) -> None:
        svc = ObservingService()
        self._stuck_safe_stop(svc, deps)
        svc.on_emergency_stop()
        snap = svc.handle_intent(IT.RESUME, deps)
        assert snap["phase"] == P.SAFE_STOPPING.value
        _wait_idle(svc, deps, timeout=10.0)
        assert deps.mount.park.call_count == 2  # window cleared → fresh park

    def test_noop_outside_safe_stopping(self, deps: ObservingDeps) -> None:
        svc = ObservingService()
        svc.on_emergency_stop()
        assert svc.snapshot()["phase"] == P.WAIT_CONTEXT_CONFIRMATION.value

    def test_guiding_stopped_only_when_issuing_park(self, deps: ObservingDeps) -> None:
        # M9-035: guiding stop ran on every 2.5 s retry pass before (log spam,
        # busy churn) — it must run only when the park is actually issued.
        deps = replace(deps, guide_role_cameras={"guide": Mock()})
        svc = ObservingService()
        self._stuck_safe_stop(svc, deps)
        for _ in range(3):  # further retry passes within the no-resend window
            _wait_idle(svc, deps, timeout=10.0)
        assert deps.guiding_service.stop.call_count == 1


class TestGuidedFlowRecordsCommands:
    """M9-032: the guided flow bypasses the /api/mount/* endpoints, so it must
    register its own commands with DeviceStateService — record_command() is
    what clears the sticky AT_HOME (and the home-promotion flags) that
    otherwise mislabel the second home cycle (hardware report 2026-07-17)."""

    def test_run_home_records_home_command(self, deps: ObservingDeps) -> None:
        svc = ObservingService()
        svc.handle_intent(IT.CONFIRM_CONTEXT, deps)
        deps.mount.get_state.return_value = MountState.AT_HOME
        svc.handle_intent(IT.START_HOME, deps)
        _wait_idle(svc, deps)
        assert deps.device_state.get_last_command()[0] == "home"

    def test_run_safe_stop_records_park_command(self, deps: ObservingDeps) -> None:
        svc = ObservingService()
        svc._phase = P.WAIT_HOME_CONFIRMATION
        deps = replace(deps, device_state=_device_state(MountState.PARKED))
        svc.handle_intent(IT.STOP_SAFELY, deps)
        _wait_idle(svc, deps, timeout=10.0)
        assert deps.device_state.get_last_command()[0] == "park"


class TestStopSafelyLabel:
    """M9-031: the STOP_SAFELY label is state-aware — offering to "park" while
    the state pill already shows PARKED read as nonsense (user feedback
    2026-07-17); the action itself is unchanged (flow exit to PARKED_SAFE)."""

    def _stop_label(self, snap: dict) -> str:
        return next(
            a["label"] for a in snap["secondary_actions"]
            if a["intent"] == IT.STOP_SAFELY.value
        )

    def test_label_when_mount_parked(self, deps: ObservingDeps) -> None:
        svc = ObservingService()
        svc._phase = P.WAIT_HOME_CONFIRMATION
        deps = replace(deps, device_state=_device_state(MountState.PARKED))
        snap = svc.snapshot(deps)
        assert self._stop_label(snap) == "End session (mount already parked)"

    def test_label_when_mount_not_parked(self, deps: ObservingDeps) -> None:
        svc = ObservingService()
        svc._phase = P.WAIT_HOME_CONFIRMATION
        deps = replace(deps, device_state=_device_state(MountState.TRACKING))
        snap = svc.snapshot(deps)
        assert self._stop_label(snap) == "Stop safely (park)"

    def test_label_default_before_first_poll(self, deps: ObservingDeps) -> None:
        svc = ObservingService()
        svc._phase = P.WAIT_CONTEXT_CONFIRMATION
        snap = svc.snapshot(deps)  # deps fixture has an unseeded device_state
        assert self._stop_label(snap) == "Stop safely (park)"


class TestUnparkContinue:
    """M9-028: PARKED_SAFE reached from the setup phases must offer a way back
    into the guided flow (user report 2026-07-17 — safe-parking at the
    "Home the mount" step left only a restart)."""

    def _park_from_wait_home(self, svc: ObservingService, deps: ObservingDeps) -> dict:
        svc._phase = P.WAIT_HOME_CONFIRMATION
        deps.device_state = _device_state(MountState.PARKED)
        svc.handle_intent(IT.STOP_SAFELY, deps)
        snap = _wait_idle(svc, deps, timeout=10.0)
        assert snap["phase"] == P.PARKED_SAFE.value
        return snap

    def test_parked_safe_offers_unpark_continue(self, deps: ObservingDeps) -> None:
        svc = ObservingService()
        snap = self._park_from_wait_home(svc, deps)
        intents = {a["intent"] for a in snap["secondary_actions"]}
        assert IT.UNPARK_CONTINUE.value in intents

    def test_unpark_continue_returns_to_wait_home_and_resets_guards(
        self, deps: ObservingDeps,
    ) -> None:
        svc = ObservingService()
        self._park_from_wait_home(svc, deps)
        snap = svc.handle_intent(IT.UNPARK_CONTINUE, deps)
        assert snap["phase"] == P.WAIT_HOME_CONFIRMATION.value
        # g8 must not leak into the next SAFE_STOPPING (would auto-advance to
        # PARKED_SAFE before the park completes); g2 home confirmation is void.
        assert snap["guards"]["g8_safe_stop_possible"] is False
        assert snap["guards"]["g2_home_confirmed"] is False
        assert snap["primary_action"]["intent"] == IT.START_HOME.value

    def test_unpark_continue_is_pure_flow_transition(self, deps: ObservingDeps) -> None:
        """The mount stays parked — the physical unpark happens later via
        home_sequence()'s auto-unpark when the user presses "Home the mount"."""
        svc = ObservingService()
        self._park_from_wait_home(svc, deps)
        deps.mount.unpark.reset_mock()
        svc.handle_intent(IT.UNPARK_CONTINUE, deps)
        deps.mount.unpark.assert_not_called()

    def test_readiness_limited_when_parked_from_setup(self, deps: ObservingDeps) -> None:
        """M9-028: green READY on a never-homed mount misled the user into
        thinking the session was complete."""
        svc = ObservingService()
        snap = self._park_from_wait_home(svc, deps)
        assert snap["guards"]["g2_home_confirmed"] is not True
        assert snap["readiness"] == "LIMITED_READY"
        assert snap["primary_action"]["label"] == "Parked safe — setup not finished"

    def test_readiness_ready_when_parked_after_confirmed_home(
        self, deps: ObservingDeps,
    ) -> None:
        svc = ObservingService()
        svc._phase = P.CAPTURE_ACTIVE
        with svc._lock:
            svc._guards = replace(svc._guards, g2_home_confirmed=True)
        deps.mount.get_state.return_value = MountState.TRACKING
        deps.device_state = _device_state(MountState.PARKED)
        svc.handle_intent(IT.STOP_SAFELY, deps)
        snap = _wait_idle(svc, deps, timeout=10.0)
        assert snap["phase"] == P.PARKED_SAFE.value
        assert snap["readiness"] == "READY"
        assert snap["primary_action"]["label"] == "Session complete — parked safe"


class TestFaultHandling:
    def test_engine_exception_transitions_to_fault(self, deps: ObservingDeps) -> None:
        svc = ObservingService()
        svc._phase = P.FOCUS_READYING
        deps.focuser.get_position.side_effect = RuntimeError("focuser jammed")
        svc.handle_intent(IT.START_FOCUS, deps)
        snap = _wait_idle(svc, deps, timeout=10.0)
        assert snap["phase"] == P.FAULT.value
        assert snap["fault_message"] is not None
        assert snap["guards"]["g9_error_recoverable"] is True

    def test_acknowledge_fault_returns_to_original_phase(self, deps: ObservingDeps) -> None:
        svc = ObservingService()
        svc._phase = P.FOCUS_READYING
        deps.focuser.get_position.side_effect = RuntimeError("focuser jammed")
        svc.handle_intent(IT.START_FOCUS, deps)
        _wait_idle(svc, deps, timeout=10.0)
        assert svc.snapshot(deps)["phase"] == P.FAULT.value

        snap = svc.handle_intent(IT.ACKNOWLEDGE_FAULT, deps)
        assert snap["phase"] == P.FOCUS_READYING.value


class TestSnapshotShape:
    def test_snapshot_has_expected_top_level_keys(self, deps: ObservingDeps) -> None:
        svc = ObservingService()
        snap = svc.snapshot(deps)
        assert set(snap) == {
            "phase", "guards", "busy", "detail", "fault_message",
            "primary_action", "secondary_actions", "readiness", "mount_state",
        }
        assert snap["primary_action"]["intent"] == IT.CONFIRM_CONTEXT.value

    # M9-029: observed mount state exposed for the phase-panel badge —
    # available already in WAIT_CONTEXT_CONFIRMATION (connecting to OnStep
    # before time/location confirmation is OK, user decision 2026-07-17).
    def test_snapshot_reports_observed_mount_state(self, deps: ObservingDeps) -> None:
        deps = replace(deps, device_state=_device_state(MountState.PARKED))
        svc = ObservingService()
        snap = svc.snapshot(deps)
        assert snap["phase"] == P.WAIT_CONTEXT_CONFIRMATION.value
        assert snap["mount_state"] == "PARKED"

    def test_snapshot_mount_state_none_before_first_poll(self, deps: ObservingDeps) -> None:
        svc = ObservingService()
        assert svc.snapshot(deps)["mount_state"] is None

    def test_snapshot_mount_state_none_without_deps(self) -> None:
        svc = ObservingService()
        assert svc.snapshot()["mount_state"] is None
