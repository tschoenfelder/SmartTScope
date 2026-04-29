"""Unit tests for the goto-and-center workflow."""
from __future__ import annotations

import pytest

from smart_telescope.domain.frame import FitsFrame
from smart_telescope.ports.solver import SolveResult
from smart_telescope.workflow.goto_center import CenterResult, _sep_arcmin, goto_and_center

import numpy as np
from astropy.io import fits


def _frame() -> FitsFrame:
    hdr = fits.Header()
    hdr["EXPTIME"] = 5.0
    return FitsFrame(pixels=np.zeros((32, 32), dtype=np.float32), header=hdr, exposure_seconds=5.0)


class _MockMount:
    def __init__(self, goto_ok: bool = True, is_slewing_seq: list[bool] | None = None) -> None:
        self._goto_ok = goto_ok
        self._slewing = list(is_slewing_seq or [False])
        self._slew_idx = 0
        self.sync_calls: list[tuple[float, float]] = []
        self.goto_calls: list[tuple[float, float]] = []

    def goto(self, ra: float, dec: float) -> bool:
        self.goto_calls.append((ra, dec))
        return self._goto_ok

    def is_slewing(self) -> bool:
        idx = min(self._slew_idx, len(self._slewing) - 1)
        self._slew_idx += 1
        return self._slewing[idx]

    def sync(self, ra: float, dec: float) -> bool:
        self.sync_calls.append((ra, dec))
        return True


class _MockCamera:
    def capture(self, exposure_seconds: float) -> FitsFrame:
        return _frame()


class _MockSolver:
    def __init__(self, results: list[SolveResult]) -> None:
        self._results = results
        self._idx = 0

    def solve(self, frame: FitsFrame, pixel_scale: float) -> SolveResult:
        r = self._results[min(self._idx, len(self._results) - 1)]
        self._idx += 1
        return r


# ── _sep_arcmin ───────────────────────────────────────────────────────────────


class TestSepArcmin:
    def test_same_point_is_zero(self) -> None:
        assert _sep_arcmin(5.0, -5.0, 5.0, -5.0) == pytest.approx(0.0, abs=1e-9)

    def test_one_degree_separation(self) -> None:
        assert _sep_arcmin(0.0, 0.0, 0.0, 1.0) == pytest.approx(60.0, rel=1e-4)

    def test_ra_separation_near_equator(self) -> None:
        # 1 hour RA = 15 deg at dec=0
        assert _sep_arcmin(0.0, 0.0, 1.0, 0.0) == pytest.approx(900.0, rel=1e-3)

    def test_symmetric(self) -> None:
        a = _sep_arcmin(5.5, -5.0, 6.0, 10.0)
        b = _sep_arcmin(6.0, 10.0, 5.5, -5.0)
        assert a == pytest.approx(b, rel=1e-9)


# ── goto_and_center ───────────────────────────────────────────────────────────


class TestGotoAndCenter:
    def _run(self, mount, camera, solver, ra=5.5, dec=-5.0, **kw):
        import asyncio
        return asyncio.get_event_loop().run_until_complete(
            goto_and_center(mount, camera, solver, ra, dec, slew_timeout_s=5.0, **kw)
        )

    def test_centers_in_one_iteration_when_already_close(self) -> None:
        solver = _MockSolver([SolveResult(success=True, ra=5.5, dec=-5.0)])
        result = self._run(_MockMount(), _MockCamera(), solver,
                           tolerance_arcmin=5.0, max_iterations=3)
        assert result.success is True
        assert result.iterations == 1

    def test_returns_center_result_type(self) -> None:
        solver = _MockSolver([SolveResult(success=True, ra=5.5, dec=-5.0)])
        result = self._run(_MockMount(), _MockCamera(), solver)
        assert isinstance(result, CenterResult)

    def test_refines_on_large_offset(self) -> None:
        # First solve: 5° off. Second solve: on target.
        solver = _MockSolver([
            SolveResult(success=True, ra=5.5, dec=-4.0),   # ~60' offset
            SolveResult(success=True, ra=5.5, dec=-5.0),   # on target
        ])
        result = self._run(_MockMount(), _MockCamera(), solver,
                           tolerance_arcmin=5.0, max_iterations=3)
        assert result.success is True
        assert result.iterations == 2

    def test_sync_called_when_offset_too_large(self) -> None:
        mount = _MockMount()
        solver = _MockSolver([
            SolveResult(success=True, ra=5.5, dec=-4.0),
            SolveResult(success=True, ra=5.5, dec=-5.0),
        ])
        self._run(mount, _MockCamera(), solver, tolerance_arcmin=5.0)
        assert len(mount.sync_calls) == 1

    def test_fails_when_goto_rejected(self) -> None:
        solver = _MockSolver([SolveResult(success=True, ra=5.5, dec=-5.0)])
        result = self._run(_MockMount(goto_ok=False), _MockCamera(), solver)
        assert result.success is False
        assert "GoTo" in (result.error or "")

    def test_fails_when_solve_fails(self) -> None:
        solver = _MockSolver([SolveResult(success=False, error="no stars")])
        result = self._run(_MockMount(), _MockCamera(), solver)
        assert result.success is False
        assert result.error is not None

    def test_fails_after_max_iterations(self) -> None:
        # Always solved far from target
        solver = _MockSolver([SolveResult(success=True, ra=5.5, dec=-4.0)] * 5)
        result = self._run(_MockMount(), _MockCamera(), solver,
                           tolerance_arcmin=0.1, max_iterations=2)
        assert result.success is False
        assert result.iterations == 2

    def test_offset_returned_is_accurate(self) -> None:
        solver = _MockSolver([SolveResult(success=True, ra=5.5, dec=-5.0)])
        result = self._run(_MockMount(), _MockCamera(), solver,
                           tolerance_arcmin=999.0, max_iterations=1)
        assert result.offset_arcmin == pytest.approx(0.0, abs=0.1)

    def test_goto_called_each_iteration(self) -> None:
        mount = _MockMount()
        solver = _MockSolver([SolveResult(success=True, ra=5.5, dec=-4.0)] * 3)
        self._run(mount, _MockCamera(), solver,
                  tolerance_arcmin=0.1, max_iterations=3)
        assert mount.goto_calls[0] == (5.5, -5.0)
