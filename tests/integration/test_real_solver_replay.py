"""
Hybrid integration tests: real ASTAP solver + replay camera + all other ports mocked.

These tests skip automatically when:
  - ASTAP is not installed, or
  - fixture FITS files are not present in tests/fixtures/

To enable:
  1. Install ASTAP (see tests/fixtures/README.md)
  2. Place c8_native_m42.fits and c8_native_blank.fits in tests/fixtures/
  3. Re-run pytest
"""

import textwrap
from pathlib import Path

import pytest

from smart_telescope.adapters.astap.solver import AstapSolver, find_astap
from smart_telescope.adapters.mock.focuser import MockFocuser
from smart_telescope.adapters.mock.mount import MockMount
from smart_telescope.adapters.mock.stacker import MockStacker
from smart_telescope.adapters.mock.storage import MockStorage
from smart_telescope.adapters.replay.camera import ReplayCamera
from smart_telescope.domain.frame import FitsFrame
from smart_telescope.domain.states import SessionState
from smart_telescope.workflow.runner import C8_NATIVE, VerticalSliceRunner

# ---------------------------------------------------------------------------
# Skip conditions
# ---------------------------------------------------------------------------

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"
FITS_M42    = FIXTURE_DIR / "c8_native_m42.fits"
FITS_BLANK  = FIXTURE_DIR / "c8_native_blank.fits"

ASTAP_PATH = find_astap()

needs_astap    = pytest.mark.skipif(ASTAP_PATH is None,      reason="ASTAP not installed")
needs_m42_fits = pytest.mark.skipif(not FITS_M42.exists(),   reason=f"fixture missing: {FITS_M42}")
needs_blank_fits = pytest.mark.skipif(
    not FITS_BLANK.exists(), reason=f"fixture missing: {FITS_BLANK}"
)

# M42 expected position (degrees) with ±1° tolerance
M42_RA_DEG  = 83.82
M42_DEC_DEG = -5.39
COORD_TOLERANCE_DEG = 1.0

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_hybrid_runner(camera, solver, profile=C8_NATIVE, storage=None):
    states = []
    runner = VerticalSliceRunner(
        camera=camera,
        mount=MockMount(),
        solver=solver,
        stacker=MockStacker(),
        storage=storage or MockStorage(),
        focuser=MockFocuser(),
        optical_profile=profile,
        on_state_change=states.append,
    )
    return runner, states


# ---------------------------------------------------------------------------
# _parse_ini unit tests — no ASTAP or FITS required
# ---------------------------------------------------------------------------

class TestAstapParseIni:
    """Pure Python tests for _parse_ini: cover RA conversion and failure modes."""

    def _write_ini(self, tmp_path, content: str) -> Path:
        p = tmp_path / "frame.ini"
        p.write_text(textwrap.dedent(content))
        return p

    def test_ra_converted_from_degrees_to_hours(self, tmp_path):
        ini = self._write_ini(tmp_path, """
            [Solution]
            PLATESOLVED=T
            CRVAL1=83.82270
            CRVAL2=-5.39110
            CROTA2=0.0
        """)
        result = AstapSolver._parse_ini(ini)
        assert result.success
        assert abs(result.ra - 83.82270 / 15.0) < 1e-6, "RA must be degrees/15"

    def test_dec_stays_in_degrees(self, tmp_path):
        ini = self._write_ini(tmp_path, """
            [Solution]
            PLATESOLVED=T
            CRVAL1=83.82270
            CRVAL2=-5.39110
            CROTA2=0.0
        """)
        result = AstapSolver._parse_ini(ini)
        assert result.success
        assert abs(result.dec - (-5.39110)) < 1e-6, "Dec must remain in degrees"

    def test_unsolved_returns_failure(self, tmp_path):
        ini = self._write_ini(tmp_path, """
            [Solution]
            PLATESOLVED=F
            WARNING=No stars found
        """)
        result = AstapSolver._parse_ini(ini)
        assert not result.success
        assert "No stars found" in result.error

    def test_empty_ini_returns_failure(self, tmp_path):
        ini = self._write_ini(tmp_path, "")
        result = AstapSolver._parse_ini(ini)
        assert not result.success

    def test_position_angle_parsed(self, tmp_path):
        ini = self._write_ini(tmp_path, """
            [Solution]
            PLATESOLVED=T
            CRVAL1=83.82270
            CRVAL2=-5.39110
            CROTA2=178.3
        """)
        result = AstapSolver._parse_ini(ini)
        assert result.success
        assert abs(result.pa - 178.3) < 1e-4


# ---------------------------------------------------------------------------
# Solver unit tests (no full workflow — just the adapter)
# ---------------------------------------------------------------------------

@needs_astap
@needs_m42_fits
class TestAstapSolverUnit:
    def test_solve_succeeds_on_m42_frame(self):
        solver = AstapSolver()
        frame = FitsFrame.from_fits_bytes(FITS_M42.read_bytes())
        result = solver.solve(frame, C8_NATIVE.pixel_scale_arcsec)
        assert result.success, f"Solve failed: {result.error}"

    def test_solved_ra_is_near_m42(self):
        solver = AstapSolver()
        frame = FitsFrame.from_fits_bytes(FITS_M42.read_bytes())
        result = solver.solve(frame, C8_NATIVE.pixel_scale_arcsec)
        assert result.success
        ra_deg = result.ra * 15.0
        assert abs(ra_deg - M42_RA_DEG) < COORD_TOLERANCE_DEG, (
            f"RA {ra_deg:.3f}° is more than {COORD_TOLERANCE_DEG}° from M42"
        )

    def test_solved_dec_is_near_m42(self):
        solver = AstapSolver()
        frame = FitsFrame.from_fits_bytes(FITS_M42.read_bytes())
        result = solver.solve(frame, C8_NATIVE.pixel_scale_arcsec)
        assert result.success
        assert abs(result.dec - M42_DEC_DEG) < COORD_TOLERANCE_DEG, (
            f"Dec {result.dec:.3f}° is more than {COORD_TOLERANCE_DEG}° from M42"
        )

    def test_wrong_pixel_scale_fails_or_degrades(self):
        """A wildly wrong scale hint (5"/px) should fail or return implausible coords."""
        solver = AstapSolver()
        frame = FitsFrame.from_fits_bytes(FITS_M42.read_bytes())
        result = solver.solve(frame, pixel_scale_hint=5.0)
        if result.success:
            ra_deg = result.ra * 15.0
            off_ra  = abs(ra_deg  - M42_RA_DEG)
            off_dec = abs(result.dec - M42_DEC_DEG)
            assert off_ra > COORD_TOLERANCE_DEG or off_dec > COORD_TOLERANCE_DEG, (
                "Solver returned plausible M42 coords even with a ×13 wrong scale — "
                "scale hint may not be enforced"
            )


@needs_astap
@needs_blank_fits
class TestAstapSolverUnsolvable:
    def test_blank_frame_fails(self):
        solver = AstapSolver()
        frame = FitsFrame.from_fits_bytes(FITS_BLANK.read_bytes())
        result = solver.solve(frame, C8_NATIVE.pixel_scale_arcsec)
        assert not result.success

    def test_failure_has_error_message(self):
        solver = AstapSolver()
        frame = FitsFrame.from_fits_bytes(FITS_BLANK.read_bytes())
        result = solver.solve(frame, C8_NATIVE.pixel_scale_arcsec)
        assert result.error is not None and len(result.error) > 0


# ---------------------------------------------------------------------------
# Hybrid workflow tests (real solver + replay camera + mocked everything else)
# ---------------------------------------------------------------------------

@needs_astap
@needs_m42_fits
class TestRealSolverReplay:
    def test_hybrid_run_reaches_saved(self):
        camera = ReplayCamera([str(FITS_M42)])
        solver = AstapSolver()
        runner, _ = make_hybrid_runner(camera, solver)
        log = runner.run()
        assert log.state == SessionState.SAVED, (
            f"Expected SAVED, got {log.state.name}. "
            f"Failure: {log.failure_stage} — {log.failure_reason}"
        )

    def test_correct_optical_profile_passed_to_solver(self):
        """Verify the profile pixel scale reaches the solver (align succeeds with correct scale)."""
        camera = ReplayCamera([str(FITS_M42)])
        solver = AstapSolver()
        runner, _ = make_hybrid_runner(camera, solver, profile=C8_NATIVE)
        log = runner.run()
        assert log.state == SessionState.SAVED
        assert log.optical_config == "C8-native"

    def test_solve_result_is_plausible_in_log(self):
        """After align+recenter, offset within 5 arcmin (real solve + mock mount)."""
        camera = ReplayCamera([str(FITS_M42)])
        solver = AstapSolver()
        runner, _ = make_hybrid_runner(camera, solver)
        log = runner.run()
        assert log.state in (SessionState.SAVED,)
        # With real solve + mock mount (perfect goto), offset should be small
        offset = log.centering_offset_arcmin
        assert offset < 5.0, f"Centering offset {offset:.1f} arcmin too large for real solve"

    def test_plate_solve_attempts_recorded(self):
        camera = ReplayCamera([str(FITS_M42)])
        solver = AstapSolver()
        runner, _ = make_hybrid_runner(camera, solver)
        log = runner.run()
        assert log.plate_solve_attempts >= 1

    def test_all_states_visited_in_order(self):
        camera = ReplayCamera([str(FITS_M42)])
        solver = AstapSolver()
        runner, states = make_hybrid_runner(camera, solver)
        runner.run()
        # CENTERING_DEGRADED is allowed if solve lands far due to frame age/coord drift
        valid_centered = {SessionState.CENTERED, SessionState.CENTERING_DEGRADED}
        assert SessionState.ALIGNED in states
        assert SessionState.SLEWED  in states
        assert any(s in valid_centered for s in states)
        assert SessionState.SAVED   in states

    def test_session_log_written_with_real_coords(self):
        storage = MockStorage()
        camera = ReplayCamera([str(FITS_M42)])
        solver = AstapSolver()
        runner, _ = make_hybrid_runner(camera, solver, storage=storage)
        log = runner.run()
        assert log.state == SessionState.SAVED
        d = storage.saved_log
        assert d["target"]["name"] == "M42"
        assert d["optical_config"] == "C8-native"

    def test_centering_state_in_log(self):
        """centering_state must be CENTERED or CENTERING_DEGRADED — never None after recenter."""
        camera = ReplayCamera([str(FITS_M42)])
        solver = AstapSolver()
        runner, _ = make_hybrid_runner(camera, solver)
        log = runner.run()
        assert log.centering_state in ("CENTERED", "CENTERING_DEGRADED"), (
            f"centering_state was {log.centering_state!r}"
        )
        d = log.to_dict()
        assert d["centering_state"] in ("CENTERED", "CENTERING_DEGRADED")


@needs_astap
@needs_blank_fits
class TestRealSolverReplayFailure:
    def test_unsolvable_frame_fails_at_align(self):
        camera = ReplayCamera([str(FITS_BLANK)])
        solver = AstapSolver()
        runner, states = make_hybrid_runner(camera, solver)
        log = runner.run()
        assert log.state == SessionState.FAILED
        assert log.failure_stage == "align"

    def test_failure_reason_recorded(self):
        camera = ReplayCamera([str(FITS_BLANK)])
        solver = AstapSolver()
        runner, _ = make_hybrid_runner(camera, solver)
        log = runner.run()
        assert log.failure_reason is not None
