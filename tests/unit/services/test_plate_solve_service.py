"""Tests for PlateSolveService (M7-006 / PS-001..PS-004 / TEST-006)."""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from smart_telescope.adapters.astap.solver import AstapSolver
from smart_telescope.domain.frame import FitsFrame
from smart_telescope.ports.solver import SolveResult
from smart_telescope.services.plate_solve_service import (
    PlateSolveError,
    PlateSolveService,
    PlateSolveState,
    SolveOutput,
)


def _frame() -> FitsFrame:
    return FitsFrame(
        pixels=np.zeros((128, 128), dtype=np.float32),
        header={},
        exposure_seconds=3.0,
    )


def _mock_solver(success: bool = True, ra: float = 5.5881, dec: float = -5.391) -> MagicMock:
    m = MagicMock(spec=AstapSolver)
    if success:
        m.solve.return_value = SolveResult(success=True, ra=ra, dec=dec, pa=0.0)
    else:
        m.solve.return_value = SolveResult(success=False, error="No pattern match")
    return m


# ── TEST-006-1: auto-gain not attempted → plate solving blocked ───────────────

def test_solve_blocked_before_autogain():
    """Plate solving raises PlateSolveError when auto-gain has not been completed."""
    svc = PlateSolveService(_mock_solver())
    with pytest.raises(PlateSolveError, match="auto-gain"):
        svc.solve(_frame(), pixel_scale_hint=0.295)
    assert svc.state == PlateSolveState.IDLE


# ── TEST-006-2: ASTAP solve succeeds → solved coordinates returned ─────────────

def test_solve_success_after_autogain():
    """After mark_autogain_complete(), a successful solve returns RA/DEC."""
    solver = _mock_solver(success=True, ra=5.5881, dec=-5.391)
    svc = PlateSolveService(solver)
    svc.mark_autogain_complete()

    result = svc.solve(_frame(), pixel_scale_hint=0.295)

    assert result.solved is True
    assert abs(result.ra - 5.5881) < 1e-4
    assert abs(result.dec - (-5.391)) < 1e-4
    assert svc.state == PlateSolveState.SUCCESS
    assert svc.retry_count == 1


# ── TEST-006-3: ASTAP solve fails → diagnostics returned ──────────────────────

def test_solve_failure_returns_diagnostics():
    """When ASTAP returns success=False, solved=False and diagnostics explain why."""
    solver = _mock_solver(success=False)
    svc = PlateSolveService(solver)
    svc.mark_autogain_complete()

    result = svc.solve(_frame(), pixel_scale_hint=0.295)

    assert result.solved is False
    assert result.diagnostics is not None
    assert svc.state == PlateSolveState.FAILED


# ── TEST-006-4: retry count increments ───────────────────────────────────────

def test_retry_count_increments():
    """Each solve() call increments retry_count regardless of outcome."""
    solver = _mock_solver(success=False)
    svc = PlateSolveService(solver)
    svc.mark_autogain_complete()

    svc.solve(_frame(), pixel_scale_hint=0.295)
    svc.solve(_frame(), pixel_scale_hint=0.295)

    assert svc.retry_count == 2


# ── TEST-006-5: reset clears all state ───────────────────────────────────────

def test_reset_clears_state():
    """reset() brings the service back to IDLE and blocks solving until auto-gain re-done."""
    solver = _mock_solver(success=True)
    svc = PlateSolveService(solver)
    svc.mark_autogain_complete()
    svc.solve(_frame(), pixel_scale_hint=0.295)
    assert svc.state == PlateSolveState.SUCCESS

    svc.reset()

    assert svc.state == PlateSolveState.IDLE
    assert svc.retry_count == 0
    assert svc.last_result is None
    with pytest.raises(PlateSolveError):
        svc.solve(_frame(), pixel_scale_hint=0.295)


# ── solver_name always ASTAP ──────────────────────────────────────────────────

def test_solver_name_is_astap():
    """solver_name in output is always 'ASTAP'."""
    svc = PlateSolveService(_mock_solver(success=True))
    svc.mark_autogain_complete()
    result = svc.solve(_frame(), pixel_scale_hint=0.295)
    assert result.solver_name == "ASTAP"
