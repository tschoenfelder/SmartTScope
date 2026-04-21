"""
Unit tests for VerticalSliceRunner — one stage at a time.

Each test class exercises a single stage method by calling it directly on a runner
whose collaborators are Mock(spec=Port) objects. This isolates the stage logic
from all other stages and from the full pipeline execution order.

Pattern:
    runner = make_unit_runner(mount=failing_mount)
    with pytest.raises(WorkflowError) as exc:
        runner._stage_initialize_mount(make_log())
    assert exc.value.stage == "initialize_mount"
"""
from unittest.mock import Mock, patch

import pytest

import smart_telescope.workflow.runner as runner_module
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
from tests.conftest import make_log, make_unit_runner

# ── Stage: connect ─────────────────────────────────────────────────────────


class TestStageConnect:
    def test_happy_path_transitions_to_connected(self):
        runner = make_unit_runner()
        log = make_log()
        runner._stage_connect(log)
        assert log.state == SessionState.CONNECTED

    def test_camera_connect_called_exactly_once(self, camera_mock):
        runner = make_unit_runner(camera=camera_mock)
        runner._stage_connect(make_log())
        camera_mock.connect.assert_called_once()

    def test_camera_failure_raises_at_connect_stage(self, camera_mock):
        camera_mock.connect.return_value = False
        runner = make_unit_runner(camera=camera_mock)
        with pytest.raises(WorkflowError) as exc:
            runner._stage_connect(make_log())
        assert exc.value.stage == "connect"
        assert "Camera" in exc.value.reason

    def test_mount_not_contacted_when_camera_fails(self, camera_mock, mount_mock):
        """Early-exit: if camera fails, mount connect must not be attempted."""
        camera_mock.connect.return_value = False
        runner = make_unit_runner(camera=camera_mock, mount=mount_mock)
        with pytest.raises(WorkflowError):
            runner._stage_connect(make_log())
        mount_mock.connect.assert_not_called()

    def test_mount_failure_raises_at_connect_stage(self, mount_mock):
        mount_mock.connect.return_value = False
        runner = make_unit_runner(mount=mount_mock)
        with pytest.raises(WorkflowError) as exc:
            runner._stage_connect(make_log())
        assert exc.value.stage == "connect"
        assert "Mount" in exc.value.reason

    def test_stage_timestamp_recorded(self):
        runner = make_unit_runner()
        log = make_log()
        runner._stage_connect(log)
        stage_names = [ts.stage for ts in log.stage_timestamps]
        assert "connect" in stage_names
        for ts in log.stage_timestamps:
            assert ts.completed_at is not None


# ── Stage: initialize_mount ────────────────────────────────────────────────


class TestStageInitializeMount:
    def test_parked_mount_calls_unpark_then_tracking(self, mount_mock):
        mount_mock.get_state.return_value = MountState.PARKED
        runner = make_unit_runner(mount=mount_mock)
        runner._stage_initialize_mount(make_log())
        mount_mock.unpark.assert_called_once()
        mount_mock.enable_tracking.assert_called_once()

    def test_unparked_mount_skips_unpark(self, mount_mock):
        mount_mock.get_state.return_value = MountState.UNPARKED
        runner = make_unit_runner(mount=mount_mock)
        runner._stage_initialize_mount(make_log())
        mount_mock.unpark.assert_not_called()
        mount_mock.enable_tracking.assert_called_once()

    def test_at_limit_raises_before_unpark(self, mount_mock):
        mount_mock.get_state.return_value = MountState.AT_LIMIT
        runner = make_unit_runner(mount=mount_mock)
        with pytest.raises(WorkflowError) as exc:
            runner._stage_initialize_mount(make_log())
        assert "limit" in exc.value.reason.lower()
        mount_mock.unpark.assert_not_called()

    def test_unpark_failure_raises_workflow_error(self, mount_mock):
        mount_mock.get_state.return_value = MountState.PARKED
        mount_mock.unpark.return_value = False
        runner = make_unit_runner(mount=mount_mock)
        with pytest.raises(WorkflowError) as exc:
            runner._stage_initialize_mount(make_log())
        assert "Unpark" in exc.value.reason

    def test_tracking_failure_raises_workflow_error(self, mount_mock):
        mount_mock.enable_tracking.return_value = False
        runner = make_unit_runner(mount=mount_mock)
        with pytest.raises(WorkflowError) as exc:
            runner._stage_initialize_mount(make_log())
        assert "tracking" in exc.value.reason.lower()

    def test_transitions_to_mount_ready(self, mount_mock):
        runner = make_unit_runner(mount=mount_mock)
        log = make_log()
        runner._stage_initialize_mount(log)
        assert log.state == SessionState.MOUNT_READY


# ── Stage: align ───────────────────────────────────────────────────────────


class TestStageAlign:
    def test_successful_first_solve_syncs_mount(self, solver_mock, mount_mock):
        runner = make_unit_runner(solver=solver_mock, mount=mount_mock)
        runner._stage_align(make_log())
        mount_mock.sync.assert_called_once_with(M42_RA, M42_DEC)

    def test_first_success_records_one_attempt(self, solver_mock):
        runner = make_unit_runner(solver=solver_mock)
        log = make_log()
        runner._stage_align(log)
        assert log.plate_solve_attempts == 1

    def test_transitions_to_aligned_on_success(self, solver_mock):
        runner = make_unit_runner(solver=solver_mock)
        log = make_log()
        runner._stage_align(log)
        assert log.state == SessionState.ALIGNED

    @pytest.mark.parametrize("profile,expected_scale", [
        (C8_NATIVE,   0.38),
        (C8_REDUCER,  0.60),
        (C8_BARLOW2X, 0.19),
    ])
    def test_pixel_scale_comes_from_optical_profile(self, solver_mock, profile, expected_scale):
        runner = make_unit_runner(solver=solver_mock, optical_profile=profile)
        runner._stage_align(make_log())
        _, actual_scale = solver_mock.solve.call_args.args
        assert actual_scale == pytest.approx(expected_scale)

    def test_first_fail_then_succeed_records_two_attempts(self, mount_mock):
        solver = Mock(spec=SolverPort)
        solver.solve.side_effect = [
            SolveResult(success=False, error="no stars"),
            SolveResult(success=True, ra=M42_RA, dec=M42_DEC),
        ]
        runner = make_unit_runner(solver=solver, mount=mount_mock)
        log = make_log()
        runner._stage_align(log)
        assert log.plate_solve_attempts == 2
        assert log.state == SessionState.ALIGNED

    def test_both_attempts_fail_raises_workflow_error(self):
        solver = Mock(spec=SolverPort)
        solver.solve.return_value = SolveResult(success=False, error="no stars")
        runner = make_unit_runner(solver=solver)
        log = make_log()
        with pytest.raises(WorkflowError) as exc:
            runner._stage_align(log)
        assert exc.value.stage == "align"
        assert log.plate_solve_attempts == SOLVE_MAX_ATTEMPTS

    def test_sync_failure_raises_workflow_error(self, solver_mock, mount_mock):
        mount_mock.sync.return_value = False
        runner = make_unit_runner(solver=solver_mock, mount=mount_mock)
        with pytest.raises(WorkflowError) as exc:
            runner._stage_align(make_log())
        assert "sync" in exc.value.reason.lower()

    def test_sync_not_called_when_solve_fails(self, mount_mock):
        solver = Mock(spec=SolverPort)
        solver.solve.return_value = SolveResult(success=False, error="no stars")
        runner = make_unit_runner(solver=solver, mount=mount_mock)
        with pytest.raises(WorkflowError):
            runner._stage_align(make_log())
        mount_mock.sync.assert_not_called()


# ── Stage: goto ────────────────────────────────────────────────────────────


class TestStageGoto:
    def test_goto_called_with_m42_coordinates(self, mount_mock):
        runner = make_unit_runner(mount=mount_mock)
        runner._stage_goto(make_log())
        mount_mock.goto.assert_called_once_with(M42_RA, M42_DEC)

    def test_goto_rejection_raises_workflow_error(self, mount_mock):
        mount_mock.goto.return_value = False
        runner = make_unit_runner(mount=mount_mock)
        with pytest.raises(WorkflowError) as exc:
            runner._stage_goto(make_log())
        assert exc.value.stage == "goto"

    def test_transitions_to_slewed(self, mount_mock):
        runner = make_unit_runner(mount=mount_mock)
        log = make_log()
        runner._stage_goto(log)
        assert log.state == SessionState.SLEWED


# ── Helper: _wait_for_slew ─────────────────────────────────────────────────


class TestWaitForSlew:
    def test_resolves_immediately_when_not_slewing(self, mount_mock):
        mount_mock.is_slewing.return_value = False
        runner = make_unit_runner(mount=mount_mock)
        runner._wait_for_slew("test_stage")
        mount_mock.is_slewing.assert_called_once()

    def test_polls_until_slewing_stops(self, mount_mock):
        mount_mock.is_slewing.side_effect = [True, True, False]
        runner = make_unit_runner(mount=mount_mock)
        with patch("smart_telescope.workflow.runner.time.sleep") as mock_sleep:
            runner._wait_for_slew("test_stage")
        assert mount_mock.is_slewing.call_count == 3
        assert mock_sleep.call_count == 2

    def test_sleep_uses_configured_interval(self, mount_mock):
        mount_mock.is_slewing.side_effect = [True, False]
        runner = make_unit_runner(mount=mount_mock)
        with patch("smart_telescope.workflow.runner.time.sleep") as mock_sleep:
            runner._wait_for_slew("test_stage")
        mock_sleep.assert_called_once_with(runner_module.SLEW_POLL_INTERVAL_S)

    def test_raises_workflow_error_on_timeout(self, mount_mock):
        mount_mock.is_slewing.return_value = True
        runner = make_unit_runner(mount=mount_mock)
        with (
            patch("smart_telescope.workflow.runner.time.sleep"),
            patch.object(runner_module, "SLEW_TIMEOUT_S", 4.0),
            patch.object(runner_module, "SLEW_POLL_INTERVAL_S", 2.0),
            pytest.raises(WorkflowError) as exc,
        ):
            runner._wait_for_slew("goto")
        assert exc.value.stage == "goto"
        assert "timed out" in exc.value.reason.lower()

    def test_timeout_error_names_duration(self, mount_mock):
        mount_mock.is_slewing.return_value = True
        runner = make_unit_runner(mount=mount_mock)
        with (
            patch("smart_telescope.workflow.runner.time.sleep"),
            patch.object(runner_module, "SLEW_TIMEOUT_S", 4.0),
            patch.object(runner_module, "SLEW_POLL_INTERVAL_S", 2.0),
            pytest.raises(WorkflowError) as exc,
        ):
            runner._wait_for_slew("goto")
        assert "4" in exc.value.reason


# ── Stage: recenter ────────────────────────────────────────────────────────


class TestStageRecenter:
    def test_centered_on_first_iteration(self, solver_mock, mount_mock):
        # Solver returns exact M42 position → offset is 0
        solver_mock.solve.return_value = SolveResult(success=True, ra=M42_RA, dec=M42_DEC)
        runner = make_unit_runner(solver=solver_mock, mount=mount_mock)
        log = make_log()
        runner._stage_recenter(log)
        assert log.state == SessionState.CENTERED
        assert log.centering_iterations == 1
        assert log.centering_offset_arcmin == pytest.approx(0.0, abs=0.01)

    def test_centered_on_second_iteration(self, mount_mock):
        far = SolveResult(success=True, ra=6.5, dec=-7.0)   # far off
        near = SolveResult(success=True, ra=M42_RA, dec=M42_DEC)  # on target
        solver = Mock(spec=SolverPort)
        solver.solve.side_effect = [far, near]
        runner = make_unit_runner(solver=solver, mount=mount_mock)
        log = make_log()
        runner._stage_recenter(log)
        assert log.state == SessionState.CENTERED
        assert log.centering_iterations == 2

    def test_correction_slew_issued_between_iterations(self, mount_mock):
        far = SolveResult(success=True, ra=6.5, dec=-7.0)
        near = SolveResult(success=True, ra=M42_RA, dec=M42_DEC)
        solver = Mock(spec=SolverPort)
        solver.solve.side_effect = [far, near]
        runner = make_unit_runner(solver=solver, mount=mount_mock)
        runner._stage_recenter(make_log())
        # goto must be called once for the correction slew
        mount_mock.goto.assert_called_once_with(M42_RA, M42_DEC)

    def test_degrades_after_max_iterations(self):
        far = SolveResult(success=True, ra=6.5, dec=-7.0)
        solver = Mock(spec=SolverPort)
        solver.solve.return_value = far
        runner = make_unit_runner(solver=solver)
        log = make_log()
        runner._stage_recenter(log)
        assert log.state == SessionState.CENTERING_DEGRADED
        assert log.centering_iterations == 3
        assert log.centering_offset_arcmin > 2.0

    def test_degraded_session_logs_warning(self):
        solver = Mock(spec=SolverPort)
        solver.solve.return_value = SolveResult(success=True, ra=6.5, dec=-7.0)
        runner = make_unit_runner(solver=solver)
        log = make_log()
        runner._stage_recenter(log)
        assert any("Centering" in w for w in log.warnings)

    def test_centering_state_is_never_none_after_recenter(self, solver_mock):
        runner = make_unit_runner(solver=solver_mock)
        log = make_log()
        runner._stage_recenter(log)
        assert log.centering_state is not None

    def test_solve_failure_during_recenter_raises_workflow_error(self):
        solver = Mock(spec=SolverPort)
        solver.solve.return_value = SolveResult(success=False, error="cloud")
        runner = make_unit_runner(solver=solver)
        with pytest.raises(WorkflowError) as exc:
            runner._stage_recenter(make_log())
        assert exc.value.stage == "recenter"

    def test_correction_slew_rejection_raises_workflow_error(self, mount_mock):
        far = SolveResult(success=True, ra=6.5, dec=-7.0)
        solver = Mock(spec=SolverPort)
        solver.solve.return_value = far
        mount_mock.goto.return_value = False
        runner = make_unit_runner(solver=solver, mount=mount_mock)
        with pytest.raises(WorkflowError) as exc:
            runner._stage_recenter(make_log())
        assert exc.value.stage == "recenter"
        assert "slew" in exc.value.reason.lower() or "correction" in exc.value.reason.lower()


# ── Stage: stack ───────────────────────────────────────────────────────────


class TestStageStack:
    def test_correct_number_of_frames_captured(self, camera_mock, stacker_mock):
        runner = make_unit_runner(camera=camera_mock, stacker=stacker_mock)
        runner._stage_stack(make_log())
        assert camera_mock.capture.call_count == runner_module.STACK_DEPTH

    def test_each_frame_uses_stack_exposure(self, camera_mock, stacker_mock):
        runner = make_unit_runner(camera=camera_mock, stacker=stacker_mock)
        runner._stage_stack(make_log())
        for c in camera_mock.capture.call_args_list:
            assert c.args[0] == pytest.approx(runner_module.STACK_EXPOSURE_S)

    def test_stacker_reset_called_before_frames(self, stacker_mock):
        runner = make_unit_runner(stacker=stacker_mock)
        runner._stage_stack(make_log())
        # reset() must be first call on stacker
        first_call = stacker_mock.method_calls[0]
        assert first_call[0] == "reset"

    def test_frames_integrated_count_recorded_in_log(self, stacker_mock):
        stacker_mock.add_frame.side_effect = [
            StackedImage(data=b"S", frames_integrated=i, frames_rejected=0)
            for i in range(1, runner_module.STACK_DEPTH + 1)
        ]
        runner = make_unit_runner(stacker=stacker_mock)
        log = make_log()
        runner._stage_stack(log)
        assert log.frames_integrated == runner_module.STACK_DEPTH

    def test_stacker_error_mid_stack_propagates(self, camera_mock, stacker_mock):
        # Stage methods raise the raw exception; run() wraps it in WorkflowError.
        # This test verifies the raw exception escapes the stage.
        # The WorkflowError wrapping is covered in tests/integration/.
        stacker_mock.add_frame.side_effect = RuntimeError("OOM during registration")
        runner = make_unit_runner(camera=camera_mock, stacker=stacker_mock)
        with pytest.raises(RuntimeError, match="OOM during registration"):
            runner._stage_stack(make_log())

    def test_transitions_to_stack_complete(self, stacker_mock):
        runner = make_unit_runner(stacker=stacker_mock)
        log = make_log()
        runner._stage_stack(log)
        assert log.state == SessionState.STACK_COMPLETE


# ── Stage: save ────────────────────────────────────────────────────────────


class TestStageSave:
    def test_image_and_log_paths_recorded(self, stacker_mock, storage_mock):
        runner = make_unit_runner(stacker=stacker_mock, storage=storage_mock)
        log = make_log()
        runner._stage_save(log)
        assert log.saved_image_path == "/data/result.png"
        assert log.saved_log_path == "/data/log.json"

    def test_disk_full_raises_workflow_error_before_write(self, storage_mock):
        storage_mock.has_free_space.return_value = False
        runner = make_unit_runner(storage=storage_mock)
        with pytest.raises(WorkflowError) as exc:
            runner._stage_save(make_log())
        assert exc.value.stage == "save"
        storage_mock.save_image.assert_not_called()

    def test_save_image_receives_stacked_data(self, stacker_mock, storage_mock):
        stacker_mock.get_current_stack.return_value = StackedImage(
            data=b"REAL_STACK", frames_integrated=10, frames_rejected=0
        )
        runner = make_unit_runner(stacker=stacker_mock, storage=storage_mock)
        runner._stage_save(make_log())
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
        runner = make_unit_runner(stacker=stacker_mock, storage=storage_mock)
        runner._stage_save(make_log())
        assert stored["saved_artifacts"]["image"] == "/data/result.png"

    def test_transitions_to_saved(self, stacker_mock, storage_mock):
        runner = make_unit_runner(stacker=stacker_mock, storage=storage_mock)
        log = make_log()
        runner._stage_save(log)
        assert log.state == SessionState.SAVED

    def test_completed_at_set_before_log_is_written(self, stacker_mock, storage_mock):
        """completed_at must appear in the stored JSON, so it must be set first."""
        stored: dict = {}

        def capture_log(log_dict, session_id):
            stored.update(log_dict)
            return "/data/log.json"

        storage_mock.save_log.side_effect = capture_log
        runner = make_unit_runner(stacker=stacker_mock, storage=storage_mock)
        runner._stage_save(make_log())
        assert stored["completed_at"] is not None
