"""Tests for plate-solve readiness pre-check (M8-020 / REQ-PS-001)."""
from __future__ import annotations

import json

import numpy as np
import pytest

from smart_telescope.domain.plate_solve_readiness import (
    READINESS_CONDITIONS,
    PlateSolveReadinessResult,
    ReadinessCondition,
)
from smart_telescope.services.plate_solve_readiness import check_plate_solve_readiness


# ── Domain ────────────────────────────────────────────────────────────────────

def test_readiness_conditions_has_8_entries():
    assert len(READINESS_CONDITIONS) == 8


def test_readiness_condition_to_dict():
    c = ReadinessCondition(name="astap_available", satisfied=False, reason="not found")
    d = c.to_dict()
    assert d == {"name": "astap_available", "satisfied": False, "reason": "not found"}


def test_plate_solve_readiness_result_ready_false_when_any_fails():
    result = PlateSolveReadinessResult(
        ready=False,
        conditions=[
            ReadinessCondition("frame_exists", True),
            ReadinessCondition("astap_available", False, "ASTAP not found"),
        ],
    )
    assert result.ready is False


def test_first_failure_returns_first_unsatisfied():
    result = PlateSolveReadinessResult(
        ready=False,
        conditions=[
            ReadinessCondition("frame_exists", True),
            ReadinessCondition("frame_saved_as_fits", False, "Not saved"),
            ReadinessCondition("astap_available", False, "Missing"),
        ],
    )
    assert result.first_failure is not None
    assert result.first_failure.name == "frame_saved_as_fits"


def test_first_failure_none_when_all_satisfied():
    result = PlateSolveReadinessResult(
        ready=True,
        conditions=[ReadinessCondition("astap_available", True)],
    )
    assert result.first_failure is None


def test_to_dict_has_expected_keys():
    result = PlateSolveReadinessResult(ready=True, conditions=[])
    d = result.to_dict()
    assert set(d.keys()) == {"ready", "conditions", "first_failure"}


def test_to_json_line():
    result = PlateSolveReadinessResult(ready=True, conditions=[])
    data = json.loads(result.to_json_line())
    assert data["ready"] is True


# ── check_plate_solve_readiness() ─────────────────────────────────────────────

def _all_kwargs(**overrides) -> dict:
    """Return kwargs that satisfy all 8 conditions, with optional overrides."""
    frame = np.zeros((64, 64), dtype=np.float32)
    defaults = dict(
        frame_pixels=frame,
        frame_fits_path="/tmp/frame.fits",
        star_count=20,
        optical_train_name="main",
        pixel_scale_arcsec=0.295,
        focal_length_mm=2000.0,
        search_radius_deg=None,
        astap_found=True,
        catalog_found=True,
        gate_allows=True,
        gate_reason=None,
        section_logger=None,
    )
    defaults.update(overrides)
    return defaults


def test_all_conditions_satisfied():
    result = check_plate_solve_readiness(**_all_kwargs())
    assert result.ready is True
    assert len(result.conditions) == 8
    assert all(c.satisfied for c in result.conditions)


def test_frame_exists_fails_when_no_frame():
    result = check_plate_solve_readiness(**_all_kwargs(frame_pixels=None))
    assert result.ready is False
    failed = [c for c in result.conditions if not c.satisfied]
    assert any(c.name == "frame_exists" for c in failed)


def test_frame_saved_as_fits_fails_when_no_path():
    result = check_plate_solve_readiness(**_all_kwargs(frame_fits_path=None))
    assert result.ready is False
    assert not _get(result, "frame_saved_as_fits").satisfied


def test_optical_train_fails_when_none():
    result = check_plate_solve_readiness(**_all_kwargs(optical_train_name=None))
    assert not _get(result, "optical_train_metadata_available").satisfied


def test_pixel_size_fails_when_none():
    result = check_plate_solve_readiness(**_all_kwargs(pixel_scale_arcsec=None))
    assert not _get(result, "pixel_size_available").satisfied


def test_focal_length_ok_with_search_radius_instead():
    result = check_plate_solve_readiness(**_all_kwargs(focal_length_mm=None, search_radius_deg=5.0))
    assert _get(result, "focal_length_or_hint_available").satisfied


def test_focal_length_fails_when_both_none():
    result = check_plate_solve_readiness(
        **_all_kwargs(focal_length_mm=None, search_radius_deg=None))
    assert not _get(result, "focal_length_or_hint_available").satisfied


def test_star_count_fails_when_none():
    result = check_plate_solve_readiness(**_all_kwargs(star_count=None))
    assert not _get(result, "star_count_measured").satisfied


def test_astap_fails_when_not_found():
    result = check_plate_solve_readiness(**_all_kwargs(astap_found=False))
    cond = _get(result, "astap_available")
    assert not cond.satisfied
    assert "ASTAP" in (cond.reason or "")


def test_astap_fails_when_catalog_missing():
    result = check_plate_solve_readiness(**_all_kwargs(astap_found=True, catalog_found=False))
    cond = _get(result, "astap_available")
    assert not cond.satisfied
    assert "catalog" in (cond.reason or "").lower()


def test_gate_fails_when_blocked():
    result = check_plate_solve_readiness(
        **_all_kwargs(gate_allows=False, gate_reason="TIME_NOT_TRUSTED"))
    cond = _get(result, "operation_gate_allows_plate_solve")
    assert not cond.satisfied
    assert "TIME_NOT_TRUSTED" in (cond.reason or "")


def test_first_failure_is_first_unsatisfied():
    result = check_plate_solve_readiness(**_all_kwargs(frame_pixels=None, frame_fits_path=None))
    assert result.first_failure is not None
    assert result.first_failure.name == "frame_exists"


def test_section_logger_called_on_run():
    """Logging is attempted when section_logger is provided."""
    import logging
    records: list[logging.LogRecord] = []

    class _Handler(logging.Handler):
        def emit(self, rec: logging.LogRecord) -> None:
            records.append(rec)

    from smart_telescope.services.section_logger import SectionLogger
    sl = SectionLogger(session_id="test-session-001")
    sl.get("plate_solve").logger.addHandler(_Handler())

    check_plate_solve_readiness(**_all_kwargs(section_logger=sl))
    assert len(records) == 1
    data = json.loads(records[0].getMessage())
    assert "ready" in data


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get(result: PlateSolveReadinessResult, name: str) -> ReadinessCondition:
    for c in result.conditions:
        if c.name == name:
            return c
    raise KeyError(f"Condition {name!r} not found in result")
