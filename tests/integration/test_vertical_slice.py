"""
Integration tests for the MVP vertical slice workflow.

Capture counts per happy-path run (RECENTER_EVERY_N_FRAMES=5, STACK_DEPTH=10,
autofocus range_steps=200, step_size=20 → 11 sweep positions):
  align             : 1   (capture #1, 5s)
  recenter          : 1   (capture #2, 10s — offset=0, passes immediately)
  autofocus sweep   : 11  (captures #3–13, one per focuser position)
  preview           : 3   (captures #14–16, 5s each)
  stack frames 1–5  : 5   (captures #17–21, 30s each)
  periodic recenter : 1   (capture #22, 10s — fires before stack frame 6)
  stack frames 6–10 : 5   (captures #23–27, 30s each)
  total             : 27
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
    SessionState.FOCUSING,        # autofocus sweep after initial centering
    SessionState.PREVIEWING,
    SessionState.STACKING,
    SessionState.CENTERED,        # periodic recenter before stack frame 6
    SessionState.STACKING,        # resume stacking
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
    # Capture call order:
    #   align(#1) recenter(#2) autofocus-sweep(#3–#13, 11 captures) preview(#14,#15,#16) stack-frame-1(#17)
    def test_fails_at_stack_stage(self):
        camera = MockCamera(fail_on_capture=17)
        runner, _ = make_runner(camera=camera)
        log = runner.run()
        assert log.state == SessionState.FAILED
        assert log.failure_stage == "stack"

    def test_failure_reason_recorded(self):
        camera = MockCamera(fail_on_capture=17)
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
# Frame quality filtering
# ---------------------------------------------------------------------------

class TestQualityFiltering:
    # Capture call order (from docstring):
    #   align(#1) recenter(#2) autofocus(#3–#13) preview(#14–#16)
    #   stack frames 1–5 (#17–#21) recenter(#22) stack frames 6–10 (#23–#27)
    # Stack frames map to captures: frame 1→#17, 2→#18, 3→#19, 4→#20, 5→#21,
    #   6→#23, 7→#24, 8→#25, 9→#26, 10→#27
    # With baseline_frames=3, frames 1–3 always pass; rejection starts at frame 4.
    # Dim captures #20 and #21 correspond to stack frames 4 and 5.

    def _make_quality_runner(self, dim_on_captures: frozenset[int]) -> VerticalSliceRunner:
        camera = MockCamera(return_bright=True, dim_on_captures=dim_on_captures)
        runner, _ = make_runner(camera=camera)
        return runner

    def test_all_bright_frames_accepted(self) -> None:
        runner = self._make_quality_runner(dim_on_captures=frozenset())
        log = runner.run()
        assert log.frames_integrated == 10
        assert log.frames_rejected == 0
        assert log.state == SessionState.SAVED

    def test_dim_frames_are_rejected(self) -> None:
        runner = self._make_quality_runner(dim_on_captures=frozenset({20, 21}))
        log = runner.run()
        assert log.frames_rejected == 2

    def test_integrated_count_excludes_rejected(self) -> None:
        runner = self._make_quality_runner(dim_on_captures=frozenset({20, 21}))
        log = runner.run()
        assert log.frames_integrated == 8

    def test_rejection_warning_logged(self) -> None:
        runner = self._make_quality_runner(dim_on_captures=frozenset({20}))
        log = runner.run()
        assert any("quality filter" in w for w in log.warnings)

    def test_session_completes_despite_rejections(self) -> None:
        runner = self._make_quality_runner(dim_on_captures=frozenset({20, 21}))
        log = runner.run()
        assert log.state == SessionState.SAVED

    def test_frame_quality_log_populated(self) -> None:
        runner = self._make_quality_runner(dim_on_captures=frozenset({20, 21}))
        log = runner.run()
        assert len(log.frame_quality_log) == 10  # one entry per stack frame
        rejected = [e for e in log.frame_quality_log if not e.accepted]
        assert len(rejected) == 2

    def test_frame_quality_log_in_serialized_dict(self) -> None:
        runner = self._make_quality_runner(dim_on_captures=frozenset({20}))
        log = runner.run()
        d = log.to_dict()
        assert "frame_quality_log" in d
        assert len(d["frame_quality_log"]) == 10
        rejected_entries = [e for e in d["frame_quality_log"] if not e["accepted"]]
        assert len(rejected_entries) == 1
        assert rejected_entries[0]["reason"] is not None


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
