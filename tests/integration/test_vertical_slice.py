"""
Integration tests for the MVP vertical slice workflow.

Capture counts per happy-path run (RECENTER_EVERY_N_FRAMES=5, STACK_DEPTH=10):
  align             : 1  (capture #1, 5s)
  recenter          : 1  (capture #2, 10s — offset=0, passes immediately)
  preview           : 3  (captures #3–5, 5s each)
  stack frames 1–5  : 5  (captures #6–10, 30s each)
  periodic recenter : 1  (capture #11, 10s — fires before stack frame 6)
  stack frames 6–10 : 5  (captures #12–16, 30s each)
  total             : 16
"""


from smart_telescope.adapters.mock.camera import MockCamera
from smart_telescope.adapters.mock.focuser import MockFocuser
from smart_telescope.adapters.mock.mount import MockMount
from smart_telescope.adapters.mock.solver import MockSolver
from smart_telescope.adapters.mock.stacker import MockStacker
from smart_telescope.adapters.mock.storage import MockStorage
from smart_telescope.domain.states import SessionState
from smart_telescope.ports.mount import MountState
from smart_telescope.ports.solver import SolveResult
from smart_telescope.workflow.runner import VerticalSliceRunner

EXPECTED_HAPPY_PATH_STATES = [
    SessionState.IDLE,
    SessionState.CONNECTED,
    SessionState.MOUNT_READY,
    SessionState.ALIGNED,
    SessionState.SLEWED,
    SessionState.CENTERED,
    SessionState.PREVIEWING,
    SessionState.STACKING,
    SessionState.CENTERED,       # periodic recenter before stack frame 6
    SessionState.STACKING,       # resume stacking
    SessionState.STACK_COMPLETE,
    SessionState.SAVED,
]


def make_runner(**overrides) -> tuple[VerticalSliceRunner, list[SessionState]]:
    states: list[SessionState] = []
    runner = VerticalSliceRunner(
        camera=overrides.get("camera", MockCamera()),
        mount=overrides.get("mount", MockMount()),
        solver=overrides.get("solver", MockSolver()),
        stacker=overrides.get("stacker", MockStacker()),
        storage=overrides.get("storage", MockStorage()),
        focuser=overrides.get("focuser", MockFocuser()),
        on_state_change=states.append,
    )
    return runner, states


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestHappyPath:
    def test_final_state_is_saved(self):
        runner, _ = make_runner()
        log = runner.run()
        assert log.state == SessionState.SAVED

    def test_all_states_visited_in_order(self):
        runner, states = make_runner()
        runner.run()
        assert states == EXPECTED_HAPPY_PATH_STATES

    def test_artifact_paths_recorded(self):
        runner, _ = make_runner()
        log = runner.run()
        assert log.saved_image_path == "/mock/session_result.png"
        assert log.saved_log_path == "/mock/session_log.json"

    def test_stack_depth_correct(self):
        runner, _ = make_runner()
        log = runner.run()
        assert log.frames_integrated == 10
        assert log.frames_rejected == 0

    def test_no_warnings_on_clean_run(self):
        runner, _ = make_runner()
        log = runner.run()
        assert log.warnings == []

    def test_centering_state_is_centered_on_clean_run(self):
        runner, _ = make_runner()
        log = runner.run()
        assert log.centering_state == "CENTERED"
        assert log.to_dict()["centering_state"] == "CENTERED"

    def test_no_failure_fields_on_success(self):
        runner, _ = make_runner()
        log = runner.run()
        assert log.failure_stage is None
        assert log.failure_reason is None

    def test_all_stages_have_completed_timestamps(self):
        runner, _ = make_runner()
        log = runner.run()
        stage_names = [ts.stage for ts in log.stage_timestamps]
        expected = (
            "connect", "initialize_mount", "align", "goto",
            "recenter", "preview", "stack", "save",
        )
        for name in expected:
            assert name in stage_names, f"Stage '{name}' missing from timestamps"
        for ts in log.stage_timestamps:
            assert ts.completed_at is not None, f"Stage '{ts.stage}' has no completed_at"
            assert ts.completed_at >= ts.started_at

    def test_session_log_serializes_to_dict(self):
        # to_dict() on the in-memory log after run — all fields are populated.
        runner, _ = make_runner()
        log = runner.run()
        d = log.to_dict()
        assert d["final_state"] == "SAVED"
        assert d["target"]["name"] == "M42"
        assert d["frames_integrated"] == 10
        assert d["saved_artifacts"]["image"] is not None
        assert d["saved_artifacts"]["log"] is not None  # log_path set on in-memory log
        assert d["completed_at"] is not None

    def test_session_log_written_to_storage(self):
        # Checks the dict that was actually persisted by storage.save_log().
        storage = MockStorage()
        runner, _ = make_runner(storage=storage)
        runner.run()
        d = storage.saved_log
        assert d["final_state"] == "SAVED"
        assert d["target"]["name"] == "M42"
        assert d["completed_at"] is not None
        assert d["saved_artifacts"]["image"] is not None
        assert d["saved_artifacts"]["log"] is None  # self-reference: log can't know its own path

    def test_starts_from_parked_mount(self):
        mount = MockMount(initial_state=MountState.PARKED)
        runner, _ = make_runner(mount=mount)
        log = runner.run()
        assert log.state == SessionState.SAVED

    def test_starts_from_already_unparked_mount(self):
        mount = MockMount(initial_state=MountState.UNPARKED)
        runner, _ = make_runner(mount=mount)
        log = runner.run()
        assert log.state == SessionState.SAVED


# ---------------------------------------------------------------------------
# Plate solve failure
# ---------------------------------------------------------------------------

class TestPlateSolveFails:
    def test_fails_at_align_stage(self):
        runner, _ = make_runner(solver=MockSolver(always_fail=True))
        log = runner.run()
        assert log.state == SessionState.FAILED
        assert log.failure_stage == "align"

    def test_saved_state_never_reached(self):
        runner, states = make_runner(solver=MockSolver(always_fail=True))
        runner.run()
        assert SessionState.SAVED not in states
        assert SessionState.FAILED in states

    def test_failure_reason_describes_solve(self):
        runner, _ = make_runner(solver=MockSolver(always_fail=True))
        log = runner.run()
        assert "Plate solve failed" in log.failure_reason

    def test_attempts_are_counted(self):
        runner, _ = make_runner(solver=MockSolver(always_fail=True))
        log = runner.run()
        assert log.plate_solve_attempts == 2  # SOLVE_MAX_ATTEMPTS


# ---------------------------------------------------------------------------
# Recentering exceeds max iterations (warning, not abort)
# ---------------------------------------------------------------------------

class TestRecenterExceedsIterations:
    # Solver always returns a position far from M42 (>2 arcmin offset)
    _far_solve = SolveResult(success=True, ra=6.5, dec=-7.0)

    def test_session_continues_to_saved(self):
        solver = MockSolver(results=[self._far_solve] * 30)
        runner, _ = make_runner(solver=solver)
        log = runner.run()
        assert log.state == SessionState.SAVED

    def test_centering_degraded_state_emitted(self):
        solver = MockSolver(results=[self._far_solve] * 30)
        runner, states = make_runner(solver=solver)
        runner.run()
        assert SessionState.CENTERING_DEGRADED in states
        assert SessionState.CENTERED not in states

    def test_centering_state_is_degraded_in_log(self):
        solver = MockSolver(results=[self._far_solve] * 30)
        runner, _ = make_runner(solver=solver)
        log = runner.run()
        assert log.centering_state == "CENTERING_DEGRADED"
        assert log.to_dict()["centering_state"] == "CENTERING_DEGRADED"

    def test_centering_warning_logged(self):
        solver = MockSolver(results=[self._far_solve] * 30)
        runner, _ = make_runner(solver=solver)
        log = runner.run()
        assert any("Centering" in w for w in log.warnings)

    def test_centering_iterations_maxed(self):
        solver = MockSolver(results=[self._far_solve] * 30)
        runner, _ = make_runner(solver=solver)
        log = runner.run()
        assert log.centering_iterations == 3

    def test_offset_recorded_in_log(self):
        solver = MockSolver(results=[self._far_solve] * 30)
        runner, _ = make_runner(solver=solver)
        log = runner.run()
        assert log.centering_offset_arcmin > 2.0


# ---------------------------------------------------------------------------
# Camera failure during stacking
# ---------------------------------------------------------------------------

class TestStackCaptureFails:
    # Capture call order: align(#1) recenter(#2) preview(#3,#4,#5) stack-frame-1(#6)
    def test_fails_at_stack_stage(self):
        camera = MockCamera(fail_on_capture=6)
        runner, _ = make_runner(camera=camera)
        log = runner.run()
        assert log.state == SessionState.FAILED
        assert log.failure_stage == "stack"

    def test_failure_reason_recorded(self):
        camera = MockCamera(fail_on_capture=6)
        runner, _ = make_runner(camera=camera)
        log = runner.run()
        assert log.failure_reason is not None


# ---------------------------------------------------------------------------
# Save failure
# ---------------------------------------------------------------------------

class TestSaveFails:
    def test_disk_full_fails_at_save_stage(self):
        runner, _ = make_runner(storage=MockStorage(disk_full=True))
        log = runner.run()
        assert log.state == SessionState.FAILED
        assert log.failure_stage == "save"

    def test_failure_reason_mentions_disk(self):
        runner, _ = make_runner(storage=MockStorage(disk_full=True))
        log = runner.run()
        assert "Disk full" in log.failure_reason

    def test_no_artifact_paths_on_disk_full(self):
        runner, _ = make_runner(storage=MockStorage(disk_full=True))
        log = runner.run()
        assert log.saved_image_path is None
        assert log.saved_log_path is None


# ---------------------------------------------------------------------------
# Mount failures
# ---------------------------------------------------------------------------

class TestMountFails:
    def test_camera_connect_failure(self):
        runner, _ = make_runner(camera=MockCamera(fail_connect=True))
        log = runner.run()
        assert log.state == SessionState.FAILED
        assert log.failure_stage == "connect"

    def test_mount_connect_failure(self):
        runner, _ = make_runner(mount=MockMount(fail_connect=True))
        log = runner.run()
        assert log.state == SessionState.FAILED
        assert log.failure_stage == "connect"

    def test_mount_at_limit_fails_initialization(self):
        runner, _ = make_runner(mount=MockMount(at_limit=True))
        log = runner.run()
        assert log.state == SessionState.FAILED
        assert log.failure_stage == "initialize_mount"
        assert "limit" in log.failure_reason.lower()

    def test_goto_rejected_fails_at_goto_stage(self):
        runner, _ = make_runner(mount=MockMount(fail_goto=True))
        log = runner.run()
        assert log.state == SessionState.FAILED
        assert log.failure_stage == "goto"
