"""
Unit tests for workflow stage functions — one stage at a time.

Each test class exercises a single stage function by calling it directly
with a StageContext whose collaborators are Mock(spec=Port) objects.
This isolates each stage from all others and from the full pipeline.

Pattern:
    ctx = make_stage_ctx(mount=failing_mount)
    with pytest.raises(WorkflowError) as exc:
        stage_initialize_mount(ctx, make_log())
    assert exc.value.stage == "initialize_mount"
"""
from unittest.mock import Mock, patch

import pytest

import smart_telescope.workflow.stages as stages_module
from smart_telescope.domain.states import SessionState
from smart_telescope.ports.mount import MountState
from smart_telescope.ports.solver import SolveResult, SolverPort
from smart_telescope.ports.stacker import StackedImage
from smart_telescope.workflow.runner import (
    C8_BARLOW2X,
    C8_NATIVE,
    C8_REDUCER,
    M42_DEC,
    M42_RA,
    SOLVE_MAX_ATTEMPTS,
    WorkflowError,
)
from smart_telescope.workflow.stages import (
    _wait_for_slew,
    stage_align,
    stage_connect,
    stage_goto,
    stage_initialize_mount,
    stage_recenter,
    stage_save,
    stage_stack,
)
from tests.conftest import make_log, make_stage_ctx, make_unit_runner

# ── Stage: connect ─────────────────────────────────────────────────────────


class TestStageConnect:
    def test_happy_path_transitions_to_connected(self):
        ctx = make_stage_ctx()
        log = make_log()
        stage_connect(ctx, log)
        assert log.state == SessionState.CONNECTED

    def test_camera_connect_called_exactly_once(self, camera_mock):
        ctx = make_stage_ctx(camera=camera_mock)
        stage_connect(ctx, make_log())
        camera_mock.connect.assert_called_once()

    def test_camera_failure_raises_at_connect_stage(self, camera_mock):
        camera_mock.connect.return_value = False
        ctx = make_stage_ctx(camera=camera_mock)
        with pytest.raises(WorkflowError) as exc:
            stage_connect(ctx, make_log())
        assert exc.value.stage == "connect"
        assert "Camera" in exc.value.reason

    def test_mount_not_contacted_when_camera_fails(self, camera_mock, mount_mock):
        """Early-exit: if camera fails, mount connect must not be attempted."""
        camera_mock.connect.return_value = False
        ctx = make_stage_ctx(camera=camera_mock, mount=mount_mock)
        with pytest.raises(WorkflowError):
            stage_connect(ctx, make_log())
        mount_mock.connect.assert_not_called()

    def test_mount_failure_raises_at_connect_stage(self, mount_mock):
        mount_mock.connect.return_value = False
        ctx = make_stage_ctx(mount=mount_mock)
        with pytest.raises(WorkflowError) as exc:
            stage_connect(ctx, make_log())
        assert exc.value.stage == "connect"
        assert "Mount" in exc.value.reason


# ── Stage: initialize_mount ────────────────────────────────────────────────


class TestStageInitializeMount:
    def test_parked_mount_calls_unpark_then_tracking(self, mount_mock):
        mount_mock.get_state.return_value = MountState.PARKED
        ctx = make_stage_ctx(mount=mount_mock)
        stage_initialize_mount(ctx, make_log())
        mount_mock.unpark.assert_called_once()
        mount_mock.enable_tracking.assert_called_once()

    def test_unparked_mount_skips_unpark(self, mount_mock):
        mount_mock.get_state.return_value = MountState.UNPARKED
        ctx = make_stage_ctx(mount=mount_mock)
        stage_initialize_mount(ctx, make_log())
        mount_mock.unpark.assert_not_called()
        mount_mock.enable_tracking.assert_called_once()

    def test_at_limit_raises_before_unpark(self, mount_mock):
        mount_mock.get_state.return_value = MountState.AT_LIMIT
        ctx = make_stage_ctx(mount=mount_mock)
        with pytest.raises(WorkflowError) as exc:
            stage_initialize_mount(ctx, make_log())
        assert "limit" in exc.value.reason.lower()
        mount_mock.unpark.assert_not_called()

    def test_unpark_failure_raises_workflow_error(self, mount_mock):
        mount_mock.get_state.return_value = MountState.PARKED
        mount_mock.unpark.return_value = False
        ctx = make_stage_ctx(mount=mount_mock)
        with pytest.raises(WorkflowError) as exc:
            stage_initialize_mount(ctx, make_log())
        assert "Unpark" in exc.value.reason

    def test_tracking_failure_raises_workflow_error(self, mount_mock):
        mount_mock.enable_tracking.return_value = False
        ctx = make_stage_ctx(mount=mount_mock)
        with pytest.raises(WorkflowError) as exc:
            stage_initialize_mount(ctx, make_log())
        assert "tracking" in exc.value.reason.lower()

    def test_transitions_to_mount_ready(self, mount_mock):
        ctx = make_stage_ctx(mount=mount_mock)
        log = make_log()
        stage_initialize_mount(ctx, log)
        assert log.state == SessionState.MOUNT_READY


# ── Stage: align ───────────────────────────────────────────────────────────


class TestStageAlign:
    def test_successful_first_solve_syncs_mount(self, solver_mock, mount_mock):
        ctx = make_stage_ctx(solver=solver_mock, mount=mount_mock)
        stage_align(ctx, make_log())
        mount_mock.sync.assert_called_once_with(M42_RA, M42_DEC)

    def test_first_success_records_one_attempt(self, solver_mock):
        ctx = make_stage_ctx(solver=solver_mock)
        log = make_log()
        stage_align(ctx, log)
        assert log.plate_solve_attempts == 1

    def test_transitions_to_aligned_on_success(self, solver_mock):
        ctx = make_stage_ctx(solver=solver_mock)
        log = make_log()
        stage_align(ctx, log)
        assert log.state == SessionState.ALIGNED

    @pytest.mark.parametrize("profile,expected_scale", [
        (C8_NATIVE,   0.38),
        (C8_REDUCER,  0.60),
        (C8_BARLOW2X, 0.19),
    ])
    def test_pixel_scale_comes_from_optical_profile(self, solver_mock, profile, expected_scale):
        ctx = make_stage_ctx(solver=solver_mock, optical_profile=profile)
        stage_align(ctx, make_log())
        _, actual_scale = solver_mock.solve.call_args.args
        assert actual_scale == pytest.approx(expected_scale)

    def test_first_fail_then_succeed_records_two_attempts(self, mount_mock):
        solver = Mock(spec=SolverPort)
        solver.solve.side_effect = [
            SolveResult(success=False, error="no stars"),
            SolveResult(success=True, ra=M42_RA, dec=M42_DEC),
        ]
        ctx = make_stage_ctx(solver=solver, mount=mount_mock)
        log = make_log()
        stage_align(ctx, log)
        assert log.plate_solve_attempts == 2
        assert log.state == SessionState.ALIGNED

    def test_both_attempts_fail_raises_workflow_error(self):
        solver = Mock(spec=SolverPort)
        solver.solve.return_value = SolveResult(success=False, error="no stars")
        ctx = make_stage_ctx(solver=solver)
        log = make_log()
        with pytest.raises(WorkflowError) as exc:
            stage_align(ctx, log)
        assert exc.value.stage == "align"
        assert log.plate_solve_attempts == SOLVE_MAX_ATTEMPTS

    def test_sync_failure_raises_workflow_error(self, solver_mock, mount_mock):
        mount_mock.sync.return_value = False
        ctx = make_stage_ctx(solver=solver_mock, mount=mount_mock)
        with pytest.raises(WorkflowError) as exc:
            stage_align(ctx, make_log())
        assert "sync" in exc.value.reason.lower()

    def test_sync_not_called_when_solve_fails(self, mount_mock):
        solver = Mock(spec=SolverPort)
        solver.solve.return_value = SolveResult(success=False, error="no stars")
        ctx = make_stage_ctx(solver=solver, mount=mount_mock)
        with pytest.raises(WorkflowError):
            stage_align(ctx, make_log())
        mount_mock.sync.assert_not_called()


# ── Stage: goto ────────────────────────────────────────────────────────────


class TestStageGoto:
    def test_goto_called_with_m42_coordinates(self, mount_mock):
        ctx = make_stage_ctx(mount=mount_mock)
        stage_goto(ctx, make_log())
        mount_mock.goto.assert_called_once_with(M42_RA, M42_DEC)

    def test_goto_uses_ctx_target_not_hardcoded(self, mount_mock):
        ctx = make_stage_ctx(mount=mount_mock, target_ra=1.0, target_dec=+45.0)
        stage_goto(ctx, make_log())
        mount_mock.goto.assert_called_once_with(1.0, +45.0)

    def test_goto_rejection_raises_workflow_error(self, mount_mock):
        mount_mock.goto.return_value = False
        ctx = make_stage_ctx(mount=mount_mock)
        with pytest.raises(WorkflowError) as exc:
            stage_goto(ctx, make_log())
        assert exc.value.stage == "goto"

    def test_transitions_to_slewed(self, mount_mock):
        ctx = make_stage_ctx(mount=mount_mock)
        log = make_log()
        stage_goto(ctx, log)
        assert log.state == SessionState.SLEWED


# ── Helper: _wait_for_slew ─────────────────────────────────────────────────


class TestWaitForSlew:
    def test_resolves_immediately_when_not_slewing(self, mount_mock):
        mount_mock.is_slewing.return_value = False
        ctx = make_stage_ctx(mount=mount_mock)
        _wait_for_slew(ctx, "test_stage")
        mount_mock.is_slewing.assert_called_once()

    def test_polls_until_slewing_stops(self, mount_mock):
        mount_mock.is_slewing.side_effect = [True, True, False]
        ctx = make_stage_ctx(mount=mount_mock)
        with patch("smart_telescope.workflow.stages.time.sleep") as mock_sleep:
            _wait_for_slew(ctx, "test_stage")
        assert mount_mock.is_slewing.call_count == 3
        assert mock_sleep.call_count == 2

    def test_sleep_uses_configured_interval(self, mount_mock):
        mount_mock.is_slewing.side_effect = [True, False]
        ctx = make_stage_ctx(mount=mount_mock)
        with patch("smart_telescope.workflow.stages.time.sleep") as mock_sleep:
            _wait_for_slew(ctx, "test_stage")
        mock_sleep.assert_called_once_with(stages_module.SLEW_POLL_INTERVAL_S)

    def test_raises_workflow_error_on_timeout(self, mount_mock):
        mount_mock.is_slewing.return_value = True
        ctx = make_stage_ctx(mount=mount_mock)
        with (
            patch("smart_telescope.workflow.stages.time.sleep"),
            patch.object(stages_module, "SLEW_TIMEOUT_S", 4.0),
            patch.object(stages_module, "SLEW_POLL_INTERVAL_S", 2.0),
            pytest.raises(WorkflowError) as exc,
        ):
            _wait_for_slew(ctx, "goto")
        assert exc.value.stage == "goto"
        assert "timed out" in exc.value.reason.lower()

    def test_timeout_error_names_duration(self, mount_mock):
        mount_mock.is_slewing.return_value = True
        ctx = make_stage_ctx(mount=mount_mock)
        with (
            patch("smart_telescope.workflow.stages.time.sleep"),
            patch.object(stages_module, "SLEW_TIMEOUT_S", 4.0),
            patch.object(stages_module, "SLEW_POLL_INTERVAL_S", 2.0),
            pytest.raises(WorkflowError) as exc,
        ):
            _wait_for_slew(ctx, "goto")
        assert "4" in exc.value.reason


# ── Stage: recenter ────────────────────────────────────────────────────────


class TestStageRecenter:
    def test_centered_on_first_iteration(self, solver_mock, mount_mock):
        solver_mock.solve.return_value = SolveResult(success=True, ra=M42_RA, dec=M42_DEC)
        ctx = make_stage_ctx(solver=solver_mock, mount=mount_mock)
        log = make_log()
        stage_recenter(ctx, log)
        assert log.state == SessionState.CENTERED
        assert log.centering_iterations == 1
        assert log.centering_offset_arcmin == pytest.approx(0.0, abs=0.01)

    def test_centered_on_second_iteration(self, mount_mock):
        far = SolveResult(success=True, ra=6.5, dec=-7.0)
        near = SolveResult(success=True, ra=M42_RA, dec=M42_DEC)
        solver = Mock(spec=SolverPort)
        solver.solve.side_effect = [far, near]
        ctx = make_stage_ctx(solver=solver, mount=mount_mock)
        log = make_log()
        stage_recenter(ctx, log)
        assert log.state == SessionState.CENTERED
        assert log.centering_iterations == 2

    def test_correction_slew_issued_between_iterations(self, mount_mock):
        far = SolveResult(success=True, ra=6.5, dec=-7.0)
        near = SolveResult(success=True, ra=M42_RA, dec=M42_DEC)
        solver = Mock(spec=SolverPort)
        solver.solve.side_effect = [far, near]
        ctx = make_stage_ctx(solver=solver, mount=mount_mock)
        stage_recenter(ctx, make_log())
        mount_mock.goto.assert_called_once_with(M42_RA, M42_DEC)

    def test_degrades_after_max_iterations(self):
        far = SolveResult(success=True, ra=6.5, dec=-7.0)
        solver = Mock(spec=SolverPort)
        solver.solve.return_value = far
        ctx = make_stage_ctx(solver=solver)
        log = make_log()
        stage_recenter(ctx, log)
        assert log.state == SessionState.CENTERING_DEGRADED
        assert log.centering_iterations == 3
        assert log.centering_offset_arcmin > 2.0

    def test_degraded_session_logs_warning(self):
        solver = Mock(spec=SolverPort)
        solver.solve.return_value = SolveResult(success=True, ra=6.5, dec=-7.0)
        ctx = make_stage_ctx(solver=solver)
        log = make_log()
        stage_recenter(ctx, log)
        assert any("Centering" in w for w in log.warnings)

    def test_centering_state_is_never_none_after_recenter(self, solver_mock):
        ctx = make_stage_ctx(solver=solver_mock)
        log = make_log()
        stage_recenter(ctx, log)
        assert log.centering_state is not None

    def test_solve_failure_during_recenter_raises_workflow_error(self):
        solver = Mock(spec=SolverPort)
        solver.solve.return_value = SolveResult(success=False, error="cloud")
        ctx = make_stage_ctx(solver=solver)
        with pytest.raises(WorkflowError) as exc:
            stage_recenter(ctx, make_log())
        assert exc.value.stage == "recenter"

    def test_correction_slew_rejection_raises_workflow_error(self, mount_mock):
        far = SolveResult(success=True, ra=6.5, dec=-7.0)
        solver = Mock(spec=SolverPort)
        solver.solve.return_value = far
        mount_mock.goto.return_value = False
        ctx = make_stage_ctx(solver=solver, mount=mount_mock)
        with pytest.raises(WorkflowError) as exc:
            stage_recenter(ctx, make_log())
        assert exc.value.stage == "recenter"
        assert "slew" in exc.value.reason.lower() or "correction" in exc.value.reason.lower()


# ── Stage: stack ───────────────────────────────────────────────────────────


class TestStageStack:
    def test_correct_number_of_frames_captured(self, camera_mock, stacker_mock):
        ctx = make_stage_ctx(camera=camera_mock, stacker=stacker_mock)
        with patch.object(stages_module, "RECENTER_EVERY_N_FRAMES", 999):
            stage_stack(ctx, make_log())
        assert camera_mock.capture.call_count == stages_module.STACK_DEPTH

    def test_each_frame_uses_stack_exposure(self, camera_mock, stacker_mock):
        ctx = make_stage_ctx(camera=camera_mock, stacker=stacker_mock)
        with patch.object(stages_module, "RECENTER_EVERY_N_FRAMES", 999):
            stage_stack(ctx, make_log())
        for c in camera_mock.capture.call_args_list:
            assert c.args[0] == pytest.approx(stages_module.STACK_EXPOSURE_S)

    def test_stacker_reset_called_before_frames(self, stacker_mock):
        ctx = make_stage_ctx(stacker=stacker_mock)
        stage_stack(ctx, make_log())
        first_call = stacker_mock.method_calls[0]
        assert first_call[0] == "reset"

    def test_frames_integrated_count_recorded_in_log(self, stacker_mock):
        stacker_mock.add_frame.side_effect = [
            StackedImage(data=b"S", frames_integrated=i, frames_rejected=0)
            for i in range(1, stages_module.STACK_DEPTH + 1)
        ]
        ctx = make_stage_ctx(stacker=stacker_mock)
        log = make_log()
        stage_stack(ctx, log)
        assert log.frames_integrated == stages_module.STACK_DEPTH

    def test_stacker_error_mid_stack_propagates(self, camera_mock, stacker_mock):
        # Stage functions raise the raw exception; run() wraps it in WorkflowError.
        stacker_mock.add_frame.side_effect = RuntimeError("OOM during registration")
        ctx = make_stage_ctx(camera=camera_mock, stacker=stacker_mock)
        with pytest.raises(RuntimeError, match="OOM during registration"):
            stage_stack(ctx, make_log())

    def test_transitions_to_stack_complete(self, stacker_mock):
        ctx = make_stage_ctx(stacker=stacker_mock)
        log = make_log()
        with patch.object(stages_module, "RECENTER_EVERY_N_FRAMES", 999):
            stage_stack(ctx, log)
        assert log.state == SessionState.STACK_COMPLETE

    def test_stop_event_set_before_start_cancels_stack(self, stacker_mock):
        import threading
        stop = threading.Event()
        stop.set()
        ctx = make_stage_ctx(stacker=stacker_mock, stop_event=stop)
        with pytest.raises(WorkflowError) as exc:
            stage_stack(ctx, make_log())
        assert exc.value.stage == "stack"
        assert "cancel" in exc.value.reason.lower() or "stop" in exc.value.reason.lower()
        stacker_mock.add_frame.assert_not_called()

    def test_tracking_lost_raises_workflow_error(self, stacker_mock, mount_mock):
        mount_mock.get_state.return_value = MountState.PARKED
        ctx = make_stage_ctx(stacker=stacker_mock, mount=mount_mock)
        with pytest.raises(WorkflowError) as exc:
            stage_stack(ctx, make_log())
        assert exc.value.stage == "stack"
        assert "tracking" in exc.value.reason.lower()

    def test_slewing_state_is_accepted_during_stack(self, stacker_mock, mount_mock):
        mount_mock.get_state.return_value = MountState.SLEWING
        ctx = make_stage_ctx(stacker=stacker_mock, mount=mount_mock)
        with patch.object(stages_module, "RECENTER_EVERY_N_FRAMES", 999):
            log = make_log()
            stage_stack(ctx, log)
        assert log.state == SessionState.STACK_COMPLETE

    def test_periodic_recenter_fires_at_configured_cadence(self, stacker_mock, mount_mock, solver_mock):
        # STACK_DEPTH=10, RECENTER_EVERY_N_FRAMES=5 → recenter fires once (before frame 6)
        solver_mock.solve.return_value = __import__(
            "smart_telescope.ports.solver", fromlist=["SolveResult"]
        ).SolveResult(success=True, ra=M42_RA, dec=M42_DEC)
        ctx = make_stage_ctx(stacker=stacker_mock, mount=mount_mock, solver=solver_mock)
        with patch.object(stages_module, "RECENTER_EVERY_N_FRAMES", 5):
            stage_stack(ctx, make_log())
        # 10 stack frames + 1 recenter capture (at iteration 6)
        assert ctx.camera.capture.call_count == stages_module.STACK_DEPTH + 1

    def test_periodic_recenter_re_transitions_to_stacking(self, stacker_mock, mount_mock, solver_mock):
        solver_mock.solve.return_value = __import__(
            "smart_telescope.ports.solver", fromlist=["SolveResult"]
        ).SolveResult(success=True, ra=M42_RA, dec=M42_DEC)
        states: list = []

        def capture_transitions(log, state):
            log.state = state
            states.append(state)

        ctx = make_stage_ctx(
            stacker=stacker_mock,
            mount=mount_mock,
            solver=solver_mock,
            on_transition=capture_transitions,
        )
        with patch.object(stages_module, "RECENTER_EVERY_N_FRAMES", 5):
            stage_stack(ctx, make_log())
        # Should see STACKING → CENTERED → STACKING (again) → STACK_COMPLETE
        assert states.count(SessionState.STACKING) >= 2
        assert SessionState.STACK_COMPLETE in states


# ── Stage: save ────────────────────────────────────────────────────────────


class TestStageSave:
    def test_image_and_log_paths_recorded(self, stacker_mock, storage_mock):
        ctx = make_stage_ctx(stacker=stacker_mock, storage=storage_mock)
        log = make_log()
        stage_save(ctx, log)
        assert log.saved_image_path == "/data/result.png"
        assert log.saved_log_path == "/data/log.json"

    def test_disk_full_raises_workflow_error_before_write(self, storage_mock):
        storage_mock.has_free_space.return_value = False
        ctx = make_stage_ctx(storage=storage_mock)
        with pytest.raises(WorkflowError) as exc:
            stage_save(ctx, make_log())
        assert exc.value.stage == "save"
        storage_mock.save_image.assert_not_called()

    def test_save_image_receives_stacked_data(self, stacker_mock, storage_mock):
        stacker_mock.get_current_stack.return_value = StackedImage(
            data=b"REAL_STACK", frames_integrated=10, frames_rejected=0
        )
        ctx = make_stage_ctx(stacker=stacker_mock, storage=storage_mock)
        stage_save(ctx, make_log())
        storage_mock.save_image.assert_called_once()
        saved_data = storage_mock.save_image.call_args.args[0]
        assert saved_data == b"REAL_STACK"

    def test_session_log_serialized_after_image_path_known(self, stacker_mock, storage_mock):
        """The stored log dict must contain the image path — ordering matters."""
        stored: dict = {}

        def capture_log(log_dict, session_id):
            stored.update(log_dict)
            return "/data/log.json"

        storage_mock.save_log.side_effect = capture_log
        ctx = make_stage_ctx(stacker=stacker_mock, storage=storage_mock)
        stage_save(ctx, make_log())
        assert stored["saved_artifacts"]["image"] == "/data/result.png"

    def test_transitions_to_saved(self, stacker_mock, storage_mock):
        ctx = make_stage_ctx(stacker=stacker_mock, storage=storage_mock)
        log = make_log()
        stage_save(ctx, log)
        assert log.state == SessionState.SAVED

    def test_completed_at_set_before_log_is_written(self, stacker_mock, storage_mock):
        """completed_at must appear in the stored JSON, so it must be set first."""
        stored: dict = {}

        def capture_log(log_dict, session_id):
            stored.update(log_dict)
            return "/data/log.json"

        storage_mock.save_log.side_effect = capture_log
        ctx = make_stage_ctx(stacker=stacker_mock, storage=storage_mock)
        stage_save(ctx, make_log())
        assert stored["completed_at"] is not None


# ── Runner orchestration ───────────────────────────────────────────────────


class TestRunnerOrchestration:
    def test_start_and_finish_stage_records_complete_timestamp(self):
        runner = make_unit_runner()
        log = make_log()
        runner._start_stage(log, "connect")
        runner._finish_stage(log, "connect")
        ts = next(t for t in log.stage_timestamps if t.stage == "connect")
        assert ts.completed_at is not None
