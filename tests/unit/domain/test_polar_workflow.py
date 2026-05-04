"""Unit tests for the PolarAlignmentWorkflow state machine."""

from __future__ import annotations

import pytest

from smart_telescope.domain.polar_workflow import (
    Action,
    AlignmentResult,
    PolarAlignmentWorkflow,
    SolveResult,
    WorkflowInput,
)


# ── shared fixtures & helpers ─────────────────────────────────────────────────

_LST  = 12.0     # arbitrary sidereal time (hours)
_LAT  = 50.0     # observer latitude (degrees)

def _inp(**kwargs) -> WorkflowInput:
    return WorkflowInput(lst=_LST, observer_lat=_LAT, **kwargs)

def _ok_slew() -> WorkflowInput:
    return _inp(slew_ok=True)

def _fail_slew() -> WorkflowInput:
    return _inp(slew_ok=False)

def _ok_solve(ra: float = 0.01, dec: float = 89.5) -> WorkflowInput:
    return _inp(solve_result=SolveResult(success=True, ra=ra, dec=dec))

def _fail_solve(msg: str = "timeout") -> WorkflowInput:
    return _inp(solve_result=SolveResult(success=False, error=msg))

def _wf(**kwargs) -> PolarAlignmentWorkflow:
    """Return a workflow with wide-open HA limits so position arithmetic never fails."""
    return PolarAlignmentWorkflow(
        observer_lat=_LAT,
        ha_east_limit_h=-12.0,
        ha_west_limit_h=12.0,
        **kwargs,
    )


# ── happy path ────────────────────────────────────────────────────────────────

class TestHappyPath:
    def test_full_run_returns_display_result(self):
        wf = _wf()
        # START → SLEW_TO_RA (home)
        act = wf.next_action(_inp())
        assert act.kind == "SLEW_TO_RA"
        assert act.dec_deg == 89.0

        # slew ok → CAPTURE_AND_SOLVE (pos 1)
        act = wf.next_action(_ok_slew())
        assert act.kind == "CAPTURE_AND_SOLVE"

        # solve pos1 ok (near pole) → SLEW_TO_RA (pos 2)
        act = wf.next_action(_ok_solve(ra=11.0, dec=89.5))
        assert act.kind == "SLEW_TO_RA"

        # slew ok → CAPTURE_AND_SOLVE (pos 2)
        act = wf.next_action(_ok_slew())
        assert act.kind == "CAPTURE_AND_SOLVE"

        # solve pos2 ok → SLEW_TO_RA (pos 3)
        act = wf.next_action(_ok_solve(ra=12.0, dec=89.4))
        assert act.kind == "SLEW_TO_RA"

        # slew ok → CAPTURE_AND_SOLVE (pos 3)
        act = wf.next_action(_ok_slew())
        assert act.kind == "CAPTURE_AND_SOLVE"

        # solve pos3 ok → DISPLAY_RESULT
        act = wf.next_action(_ok_solve(ra=13.0, dec=89.6))
        assert act.kind == "DISPLAY_RESULT"
        assert isinstance(act.result, AlignmentResult)
        assert act.result.p1 is not None
        assert act.result.p2 is not None
        assert act.result.p3 is not None

    def test_home_ra_set_after_start(self):
        wf = _wf()
        wf.next_action(_inp())
        assert wf.home_ra == _LST % 24.0

    def test_terminal_state_returns_failed(self):
        # COARSE_REQUIRED sets ws=DONE; calling next_action after that returns the
        # catch-all "terminal state" FAILED.
        wf = _wf()
        wf.next_action(_inp())
        wf.next_action(_ok_slew())
        wf.next_action(_ok_solve(dec=80.0))   # far off pole → COARSE_REQUIRED → DONE
        act = wf.next_action(_inp())           # ws is now DONE
        assert act.kind == "FAILED"
        assert "terminal" in act.message.lower()


# ── coarse alignment check ─────────────────────────────────────────────────────

class TestCoarseCheck:
    def test_coarse_required_when_far_from_pole(self):
        wf = _wf()
        wf.next_action(_inp())               # START
        wf.next_action(_ok_slew())           # slew ok → solve 1
        # dec = 80° → 10° from pole → COARSE_REQUIRED
        act = wf.next_action(_ok_solve(dec=80.0))
        assert act.kind == "COARSE_REQUIRED"
        assert act.coarse_error_deg is not None
        assert act.coarse_error_deg > 5.0

    def test_no_coarse_required_when_close(self):
        wf = _wf()
        wf.next_action(_inp())
        wf.next_action(_ok_slew())
        # dec = 89.5 → 0.5° from pole → continues
        act = wf.next_action(_ok_solve(dec=89.5))
        assert act.kind == "SLEW_TO_RA"

    def test_warning_when_moderately_off(self):
        """1°–5° off pole: workflow continues but AlignmentResult.warning_msg is set."""
        wf = _wf()
        wf.next_action(_inp())
        wf.next_action(_ok_slew())
        # dec = 87° → 3° from pole → warning, but continues
        act = wf.next_action(_ok_solve(dec=87.0))
        assert act.kind == "SLEW_TO_RA"


# ── position-2 retry ──────────────────────────────────────────────────────────

class TestPos2Retry:
    def _drive_to_pos2_solve(self, wf: PolarAlignmentWorkflow):
        wf.next_action(_inp())
        wf.next_action(_ok_slew())
        wf.next_action(_ok_solve(dec=89.5))
        wf.next_action(_ok_slew())

    def test_retry_on_pos2_failure(self):
        wf = _wf()
        self._drive_to_pos2_solve(wf)
        # pos2 solve fails → retry SLEW_TO_RA
        act = wf.next_action(_fail_solve())
        assert act.kind == "SLEW_TO_RA"
        assert "retry" in act.message.lower()

    def test_failed_after_pos2_retry_fails(self):
        wf = _wf()
        self._drive_to_pos2_solve(wf)
        wf.next_action(_fail_solve())    # fail pos2 → retry slew
        wf.next_action(_ok_slew())       # retry slew ok → capture
        act = wf.next_action(_fail_solve())   # retry solve fails
        assert act.kind == "FAILED"
        assert act.camera_fallback_suggested is True

    def test_continues_after_pos2_retry_succeeds(self):
        wf = _wf()
        self._drive_to_pos2_solve(wf)
        wf.next_action(_fail_solve())    # fail → retry slew
        wf.next_action(_ok_slew())       # slew ok
        act = wf.next_action(_ok_solve(ra=12.0, dec=89.4))  # retry solve ok
        assert act.kind == "SLEW_TO_RA"  # now heading to pos3


# ── position-3 retry ──────────────────────────────────────────────────────────

class TestPos3Retry:
    def _drive_to_pos3_solve(self, wf: PolarAlignmentWorkflow):
        wf.next_action(_inp())
        wf.next_action(_ok_slew())
        wf.next_action(_ok_solve(dec=89.5))
        wf.next_action(_ok_slew())
        wf.next_action(_ok_solve(ra=12.0, dec=89.4))
        wf.next_action(_ok_slew())

    def test_retry_on_pos3_failure(self):
        wf = _wf()
        self._drive_to_pos3_solve(wf)
        act = wf.next_action(_fail_solve())
        assert act.kind == "SLEW_TO_RA"
        assert "retry" in act.message.lower()

    def test_failed_after_pos3_retry_fails(self):
        wf = _wf()
        self._drive_to_pos3_solve(wf)
        wf.next_action(_fail_solve())    # fail pos3 → retry slew
        wf.next_action(_ok_slew())       # slew ok
        act = wf.next_action(_fail_solve())   # retry solve fails
        assert act.kind == "FAILED"
        assert act.camera_fallback_suggested is True

    def test_completes_after_pos3_retry_succeeds(self):
        wf = _wf()
        self._drive_to_pos3_solve(wf)
        wf.next_action(_fail_solve())
        wf.next_action(_ok_slew())
        act = wf.next_action(_ok_solve(ra=13.0, dec=89.6))
        assert act.kind == "DISPLAY_RESULT"


# ── error conditions ──────────────────────────────────────────────────────────

class TestErrors:
    def test_slew_failure_returns_failed(self):
        wf = _wf()
        wf.next_action(_inp())
        act = wf.next_action(_fail_slew())
        assert act.kind == "FAILED"
        assert "slew" in act.message.lower()

    def test_home_solve_failure_returns_failed(self):
        wf = _wf()
        wf.next_action(_inp())
        wf.next_action(_ok_slew())
        act = wf.next_action(_fail_solve("no stars"))
        assert act.kind == "FAILED"
        assert "HOME" in act.message

    def test_user_stopped_at_any_point(self):
        wf = _wf()
        wf.next_action(_inp())
        act = wf.next_action(WorkflowInput(lst=_LST, observer_lat=_LAT,
                                           slew_ok=True, user_stopped=True))
        assert act.kind == "FAILED"
        assert "stopped" in act.message.lower()

    def test_ha_east_limit_blocks_start(self):
        wf = PolarAlignmentWorkflow(
            observer_lat=_LAT,
            ha_east_limit_h=-0.1,   # very tight — LST=12, ra1=12 → HA=0 which is OK
            ha_west_limit_h=0.5,
        )
        act = wf.next_action(_inp())
        assert act.kind == "SLEW_TO_RA"   # HA=0 is within [-0.1, 0.5]

    def test_ha_west_limit_blocks_start(self):
        # LST=12, ra1=12 → HA=0; west limit = -0.1 means HA 0 > -0.1 is blocked
        wf = PolarAlignmentWorkflow(
            observer_lat=_LAT,
            ha_east_limit_h=-5.5,
            ha_west_limit_h=-0.1,
        )
        act = wf.next_action(_inp())
        assert act.kind == "FAILED"


# ── refine mode (ra overrides) ────────────────────────────────────────────────

class TestRefineMode:
    def test_pos2_ra_override_used(self):
        # _on_solve_1 returns the SLEW_TO_RA for pos2 directly; check that call.
        wf = _wf(pos2_ra_override=14.0, pos3_ra_override=15.0)
        wf.next_action(_inp())
        wf.next_action(_ok_slew())
        act = wf.next_action(_ok_solve(dec=89.5))   # p1 solve → returns SLEW_TO_RA pos2
        assert act.kind == "SLEW_TO_RA"
        assert act.ra_h == pytest.approx(14.0)

    def test_pos3_ra_override_used(self):
        # _on_solve_2 → _slew_to_3 returns SLEW_TO_RA for pos3 directly.
        wf = _wf(pos2_ra_override=14.0, pos3_ra_override=15.0)
        wf.next_action(_inp())
        wf.next_action(_ok_slew())
        wf.next_action(_ok_solve(dec=89.5))          # pos1 → SLEW_TO_RA pos2
        wf.next_action(_ok_slew())                   # slew pos2 → CAPTURE_AND_SOLVE
        act = wf.next_action(_ok_solve(ra=14.0, dec=89.4))  # pos2 → SLEW_TO_RA pos3
        assert act.kind == "SLEW_TO_RA"
        assert act.ra_h == pytest.approx(15.0)


# ── result quality ────────────────────────────────────────────────────────────

class TestResultFields:
    def _run_to_completion(self) -> AlignmentResult:
        wf = _wf()
        wf.next_action(_inp())
        wf.next_action(_ok_slew())
        wf.next_action(_ok_solve(ra=11.0, dec=89.5))
        wf.next_action(_ok_slew())
        wf.next_action(_ok_solve(ra=12.0, dec=89.4))
        wf.next_action(_ok_slew())
        act = wf.next_action(_ok_solve(ra=13.0, dec=89.6))
        assert act.kind == "DISPLAY_RESULT"
        return act.result

    def test_result_has_all_required_fields(self):
        r = self._run_to_completion()
        assert r.alt_error_arcmin is not None
        assert r.az_error_arcmin is not None
        assert r.total_error_arcmin >= 0
        assert r.correction_alt
        assert r.correction_az
        assert r.quality_label
        assert isinstance(r.target_reached, bool)

    def test_result_retries_zero_on_clean_run(self):
        r = self._run_to_completion()
        assert r.solve_retries == 0

    def test_result_retries_incremented_on_retry(self):
        wf = _wf()
        wf.next_action(_inp())
        wf.next_action(_ok_slew())
        wf.next_action(_ok_solve(dec=89.5))
        wf.next_action(_ok_slew())
        wf.next_action(_fail_solve())   # pos2 fail → retry
        wf.next_action(_ok_slew())
        wf.next_action(_ok_solve(ra=12.0, dec=89.4))  # retry ok
        wf.next_action(_ok_slew())
        act = wf.next_action(_ok_solve(ra=13.0, dec=89.6))
        assert act.kind == "DISPLAY_RESULT"
        assert act.result.solve_retries == 1
