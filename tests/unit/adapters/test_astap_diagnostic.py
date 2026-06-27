"""Tests for AstapSolveRecord and AstapSolver structured diagnostics (M8-021)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from smart_telescope.domain.astap_diagnostic import AstapSolveRecord
from smart_telescope.domain.frame import FitsFrame
from smart_telescope.ports.solver import SolveResult


# ── AstapSolveRecord domain tests ─────────────────────────────────────────────

def _make_record(**kwargs) -> AstapSolveRecord:
    defaults = dict(
        fits_path="/tmp/frame.fits",
        command=["astap", "-f", "/tmp/frame.fits"],
        exit_code=0,
        stdout="",
        stderr="",
        duration_ms=123.4,
        star_count=20,
        min_stars_threshold=15,
        star_count_gate_passed=True,
        solve_success=True,
        ra_hours=5.0,
        dec_deg=45.0,
        error=None,
    )
    defaults.update(kwargs)
    return AstapSolveRecord(**defaults)


def test_record_to_dict_has_all_keys():
    r = _make_record()
    d = r.to_dict()
    expected = {
        "fits_path", "command", "exit_code", "stdout", "stderr",
        "duration_ms", "star_count", "min_stars_threshold",
        "star_count_gate_passed", "solve_success", "ra_hours", "dec_deg", "error",
    }
    assert set(d.keys()) == expected


def test_record_to_json_line_round_trips():
    r = _make_record()
    data = json.loads(r.to_json_line())
    assert data["solve_success"] is True
    assert data["ra_hours"] == 5.0


def test_record_star_count_gate_none_when_not_measured():
    r = _make_record(star_count=None, star_count_gate_passed=None)
    assert r.to_dict()["star_count"] is None
    assert r.to_dict()["star_count_gate_passed"] is None


def test_record_failure_fields():
    r = _make_record(
        solve_success=False, ra_hours=None, dec_deg=None,
        error="PLATESOLVED=F", exit_code=1,
    )
    d = r.to_dict()
    assert d["solve_success"] is False
    assert d["error"] == "PLATESOLVED=F"


# ── SolveResult.diagnostics field ─────────────────────────────────────────────

def test_solve_result_diagnostics_default_none():
    r = SolveResult(success=True)
    assert r.diagnostics is None


def test_solve_result_accepts_diagnostics():
    rec = _make_record()
    r = SolveResult(success=True, diagnostics=rec)
    assert r.diagnostics is rec


# ── AstapSolver integration: structured logging ────────────────────────────────

@pytest.fixture()
def _frame():
    pixels = np.zeros((64, 64), dtype=np.float32)
    return FitsFrame(pixels=pixels, header={}, exposure_seconds=1.0)


def _ini_content(solved: bool = True, ra: float = 75.0, dec: float = 45.0) -> str:
    if solved:
        return f"[Solution]\nPLATESOLVED=T\nCRVAL1={ra}\nCRVAL2={dec}\nCROTA2=0\n"
    return "[Solution]\nPLATESOLVED=F\nWARNING=No match\n"


def _make_mock_proc(exit_code=0, stdout="", stderr="") -> MagicMock:
    proc = MagicMock()
    proc.returncode = exit_code
    proc.stdout = stdout
    proc.stderr = stderr
    return proc


def _patch_run(proc: MagicMock, ini_content: str | None = None):
    """Patch subprocess.run and optionally also patch Path.write_bytes / with_suffix."""
    return patch("smart_telescope.adapters.astap.solver.subprocess.run", return_value=proc)


def test_solve_attaches_diagnostics_on_success(_frame):
    from smart_telescope.adapters.astap.solver import AstapSolver

    ini = _ini_content(solved=True)
    with patch("smart_telescope.adapters.astap.solver.subprocess.run", return_value=_make_mock_proc(0)) as mock_run, \
         patch("smart_telescope.adapters.astap.solver.find_catalog", return_value=None), \
         patch.object(Path, "write_bytes"), \
         patch.object(Path, "exists", return_value=True), \
         patch.object(Path, "with_suffix", return_value=MagicMock(
             exists=lambda: True,
             read_text=lambda **_: ini,
         )):
        solver = AstapSolver(astap_path="/fake/astap", timeout_seconds=5)
        result = solver.solve(_frame, pixel_scale_hint=0.295)

    assert result.success is True
    assert result.diagnostics is not None
    assert result.diagnostics.solve_success is True
    assert result.diagnostics.exit_code == 0


def test_solve_attaches_diagnostics_on_timeout(_frame):
    from smart_telescope.adapters.astap.solver import AstapSolver

    with patch("smart_telescope.adapters.astap.solver.subprocess.run",
               side_effect=subprocess.TimeoutExpired(cmd="astap", timeout=5)), \
         patch("smart_telescope.adapters.astap.solver.find_catalog", return_value=None), \
         patch.object(Path, "write_bytes"):
        solver = AstapSolver(astap_path="/fake/astap", timeout_seconds=5)
        result = solver.solve(_frame, pixel_scale_hint=0.295)

    assert result.success is False
    assert result.diagnostics is not None
    assert "timed out" in (result.diagnostics.error or "")
    assert result.diagnostics.exit_code == -1


def test_solve_attaches_diagnostics_on_launch_failure(_frame):
    from smart_telescope.adapters.astap.solver import AstapSolver

    with patch("smart_telescope.adapters.astap.solver.subprocess.run",
               side_effect=OSError("No such file")), \
         patch("smart_telescope.adapters.astap.solver.find_catalog", return_value=None), \
         patch.object(Path, "write_bytes"):
        solver = AstapSolver(astap_path="/fake/astap", timeout_seconds=5)
        result = solver.solve(_frame, pixel_scale_hint=0.295)

    assert result.success is False
    assert result.diagnostics is not None
    assert "launch failed" in (result.diagnostics.error or "")


def test_solve_star_count_gate_passed(_frame):
    """Star count above threshold → gate_passed=True in diagnostics."""
    from smart_telescope.adapters.astap.solver import AstapSolver

    ini = _ini_content(solved=True)
    with patch("smart_telescope.adapters.astap.solver.subprocess.run", return_value=_make_mock_proc(0)), \
         patch("smart_telescope.adapters.astap.solver.find_catalog", return_value=None), \
         patch.object(Path, "write_bytes"), \
         patch.object(Path, "exists", return_value=True), \
         patch.object(Path, "with_suffix", return_value=MagicMock(
             exists=lambda: True,
             read_text=lambda **_: ini,
         )):
        solver = AstapSolver(astap_path="/fake/astap", timeout_seconds=5)
        result = solver.solve(_frame, pixel_scale_hint=0.295, star_count=20, min_stars=15)

    assert result.diagnostics is not None
    assert result.diagnostics.star_count == 20
    assert result.diagnostics.star_count_gate_passed is True


def test_solve_star_count_below_threshold_still_proceeds(_frame):
    """Below threshold with allow_below_min_stars=True → proceed, gate_passed=False."""
    from smart_telescope.adapters.astap.solver import AstapSolver

    ini = _ini_content(solved=True)
    with patch("smart_telescope.adapters.astap.solver.subprocess.run", return_value=_make_mock_proc(0)), \
         patch("smart_telescope.adapters.astap.solver.find_catalog", return_value=None), \
         patch.object(Path, "write_bytes"), \
         patch.object(Path, "exists", return_value=True), \
         patch.object(Path, "with_suffix", return_value=MagicMock(
             exists=lambda: True,
             read_text=lambda **_: ini,
         )):
        solver = AstapSolver(astap_path="/fake/astap", timeout_seconds=5)
        result = solver.solve(
            _frame, pixel_scale_hint=0.295,
            star_count=5, min_stars=15, allow_below_min_stars=True,
        )

    assert result.diagnostics is not None
    assert result.diagnostics.star_count_gate_passed is False
    # Solve still ran and succeeded
    assert result.success is True


def test_solve_blocked_when_allow_below_min_stars_false(_frame):
    """Below threshold with allow_below_min_stars=False → return failure immediately."""
    from smart_telescope.adapters.astap.solver import AstapSolver

    with patch("smart_telescope.adapters.astap.solver.find_catalog", return_value=None):
        solver = AstapSolver(astap_path="/fake/astap", timeout_seconds=5)
        result = solver.solve(
            _frame, pixel_scale_hint=0.295,
            star_count=3, min_stars=15, allow_below_min_stars=False,
        )

    assert result.success is False
    assert "below minimum" in (result.error or "")


def test_config_has_plate_solve_keys():
    from smart_telescope import config
    assert hasattr(config, "MIN_DETECTED_STARS_BEFORE_SOLVE")
    assert hasattr(config, "ALLOW_ASTAP_BELOW_MIN_STAR_COUNT")
    assert config.MIN_DETECTED_STARS_BEFORE_SOLVE == 15
    assert config.ALLOW_ASTAP_BELOW_MIN_STAR_COUNT is True
