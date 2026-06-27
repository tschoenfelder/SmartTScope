"""Tests for CameraDiagnosticReport (M8-019 / REQ-SETUP-001..002)."""
from __future__ import annotations

import numpy as np
import pytest

from smart_telescope.domain.camera_diagnostic import (
    CameraDiagnosticReport,
    CameraDiagnosticStatus,
)
from smart_telescope.services.setup_check_service import (
    MIN_STARS_BEFORE_SOLVE,
    _analyse_frame,
    run_camera_diagnostic,
)


# ── Domain ────────────────────────────────────────────────────────────────────

def test_camera_diagnostic_status_enum_has_all_10_values():
    values = {s.value for s in CameraDiagnosticStatus}
    expected = {
        "not_attempted", "disconnected", "inactive", "operation_blocked",
        "capture_failed", "auto_gain_failed", "insufficient_stars",
        "metadata_missing", "astap_failed", "solved",
    }
    assert values == expected


def test_camera_diagnostic_report_to_dict_has_19_fields():
    rep = CameraDiagnosticReport(
        camera_id="cam0", camera_role="main", optical_train_id="main",
        camera_index=0, is_enabled_in_config=True, is_assigned_to_train=True,
        is_sdk_detected=True, status=CameraDiagnosticStatus.NOT_ATTEMPTED,
    )
    d = rep.to_dict()
    assert len(d) == 19, sorted(d.keys())


def test_camera_diagnostic_report_to_json_line():
    import json
    rep = CameraDiagnosticReport(
        camera_id="cam0", camera_role="main", optical_train_id="main",
        camera_index=0, is_enabled_in_config=True, is_assigned_to_train=True,
        is_sdk_detected=True, status=CameraDiagnosticStatus.SOLVED,
        ra_hours=5.6, dec_deg=-5.4,
    )
    data = json.loads(rep.to_json_line())
    assert data["status"] == "solved"
    assert data["ra_hours"] == 5.6


# ── _analyse_frame() ──────────────────────────────────────────────────────────

def _make_frame_with_stars(n_stars: int = 20, size: int = 512) -> np.ndarray:
    """Synthetic frame: flat background + grid-placed point-source stars.

    Uses a uniform grid to avoid overlapping blobs so star count is reliable.
    """
    frame = np.full((size, size), 120.0, dtype=np.float32)
    # Place stars on a regular grid; spacing ensures no blob overlaps.
    cols = int(np.ceil(np.sqrt(n_stars)))
    spacing = size // (cols + 1)
    placed = 0
    for row in range(1, cols + 2):
        for col in range(1, cols + 2):
            if placed >= n_stars:
                break
            y = row * spacing
            x = col * spacing
            if 5 <= y < size - 5 and 5 <= x < size - 5:
                frame[y - 1:y + 2, x - 1:x + 2] = 5000  # bright 3x3 blob
                placed += 1
    return frame


def test_analyse_frame_detects_stars():
    frame = _make_frame_with_stars(n_stars=25)
    count, fwhm, bg = _analyse_frame(frame)
    assert count > 0, "Expected at least one star detected"
    assert isinstance(bg, float)


def test_analyse_frame_dark_frame_no_stars():
    frame = np.zeros((128, 128), dtype=np.float32) + 100.0
    count, fwhm, bg = _analyse_frame(frame)
    assert count == 0


def test_analyse_frame_returns_background():
    frame = np.full((64, 64), 500.0, dtype=np.float32)
    _, _, bg = _analyse_frame(frame)
    assert abs(bg - 500.0) < 1.0


def test_analyse_frame_3d_rgb_reduced_to_2d():
    frame_3d = np.zeros((64, 64, 3), dtype=np.float32) + 100.0
    count, fwhm, bg = _analyse_frame(frame_3d)
    assert isinstance(count, int)


# ── run_camera_diagnostic() ───────────────────────────────────────────────────

class _MockTrain:
    def __init__(self, name="main", camera_role="main", camera_index=0,
                 pixel_scale_arcsec=0.295, camera_id="MockCam"):
        self.name = name
        self.camera_role = camera_role
        self.camera_index = camera_index
        self.pixel_scale_arcsec = pixel_scale_arcsec
        self.camera_id = camera_id


class _MockRegistry:
    def __init__(self, trains):
        self._trains = trains
    def all(self):
        return self._trains


class _MockCamera:
    def __init__(self, should_fail=False):
        self._fail = should_fail
    def capture(self, exposure_s):
        if self._fail:
            raise RuntimeError("Camera disconnected")
        from smart_telescope.domain.frame import FitsFrame
        pixels = _make_frame_with_stars(n_stars=20)
        return FitsFrame(pixels=pixels, header={}, exposure_seconds=exposure_s)


class _MockRuntime:
    def __init__(self, camera=None, fail_camera=False):
        self._camera = camera or _MockCamera()
        self._fail = fail_camera
    def get_camera_by_role(self, role):
        if self._fail:
            raise RuntimeError("Not detected")
        return self._camera


class _MockSolveResult:
    def __init__(self, success=True):
        self.success = success
        self.ra = 5.6
        self.dec = -5.4
        self.pa = 0.0
        self.error = None


class _MockSolver:
    def __init__(self, success=True, fail=False):
        self._success = success
        self._fail = fail
    def solve(self, frame, pixel_scale, **kwargs):
        if self._fail:
            raise RuntimeError("ASTAP not found")
        return _MockSolveResult(success=self._success)


def _mock_ds():
    return object()


def test_run_camera_diagnostic_empty_registry():
    registry = _MockRegistry([])
    reports = run_camera_diagnostic(registry, _MockRuntime(), _MockSolver(), _mock_ds())
    assert reports == []


def test_run_camera_diagnostic_disconnected_camera():
    registry = _MockRegistry([_MockTrain()])
    rt = _MockRuntime(fail_camera=True)
    reports = run_camera_diagnostic(registry, rt, _MockSolver(), _mock_ds())
    assert len(reports) == 1
    assert reports[0].status == CameraDiagnosticStatus.DISCONNECTED
    assert reports[0].is_sdk_detected is False


def test_run_camera_diagnostic_capture_failed():
    registry = _MockRegistry([_MockTrain()])
    rt = _MockRuntime(camera=_MockCamera(should_fail=True))
    reports = run_camera_diagnostic(registry, rt, _MockSolver(), _mock_ds())
    assert reports[0].status == CameraDiagnosticStatus.CAPTURE_FAILED


def test_run_camera_diagnostic_astap_failed(monkeypatch):
    monkeypatch.setattr(
        "smart_telescope.services.setup_check_service._analyse_frame",
        lambda data: (20, 2.0, 120.0),
    )
    registry = _MockRegistry([_MockTrain()])
    rt = _MockRuntime()
    reports = run_camera_diagnostic(
        registry, rt, _MockSolver(success=False), _mock_ds(),
    )
    assert reports[0].status == CameraDiagnosticStatus.ASTAP_FAILED


def test_run_camera_diagnostic_solver_exception(monkeypatch):
    monkeypatch.setattr(
        "smart_telescope.services.setup_check_service._analyse_frame",
        lambda data: (20, 2.0, 120.0),
    )
    registry = _MockRegistry([_MockTrain()])
    rt = _MockRuntime()
    reports = run_camera_diagnostic(
        registry, rt, _MockSolver(fail=True), _mock_ds(),
    )
    assert reports[0].status == CameraDiagnosticStatus.ASTAP_FAILED


def test_run_camera_diagnostic_solved(monkeypatch):
    monkeypatch.setattr(
        "smart_telescope.services.setup_check_service._analyse_frame",
        lambda data: (20, 2.0, 120.0),
    )
    registry = _MockRegistry([_MockTrain()])
    rt = _MockRuntime()
    reports = run_camera_diagnostic(
        registry, rt, _MockSolver(success=True), _mock_ds(),
    )
    r = reports[0]
    assert r.status == CameraDiagnosticStatus.SOLVED
    assert r.ra_hours == 5.6
    assert r.dec_deg  == -5.4


def test_run_camera_diagnostic_metadata_missing_no_pixel_scale(monkeypatch):
    train = _MockTrain()
    train.pixel_scale_arcsec = None
    registry = _MockRegistry([train])
    # Override frame analysis to return high star count so the pixel_scale check is reached.
    monkeypatch.setattr(
        "smart_telescope.services.setup_check_service._analyse_frame",
        lambda data: (20, 2.0, 120.0),
    )
    reports = run_camera_diagnostic(registry, _MockRuntime(), _MockSolver(), _mock_ds())
    assert reports[0].status == CameraDiagnosticStatus.METADATA_MISSING


def test_run_camera_diagnostic_operation_blocked():
    registry = _MockRegistry([_MockTrain()])
    from fastapi import HTTPException
    def gate_fn(role):
        raise HTTPException(status_code=403, detail={"reason_code": "TIME_NOT_TRUSTED"})
    reports = run_camera_diagnostic(
        registry, _MockRuntime(), _MockSolver(), _mock_ds(),
        gate_check_fn=gate_fn,
    )
    assert reports[0].status == CameraDiagnosticStatus.OPERATION_BLOCKED


def test_run_camera_diagnostic_multiple_cameras(monkeypatch):
    monkeypatch.setattr(
        "smart_telescope.services.setup_check_service._analyse_frame",
        lambda data: (20, 2.0, 120.0),
    )
    trains = [_MockTrain("main", "main", 0), _MockTrain("guide", "guide", 1)]
    registry = _MockRegistry(trains)
    reports = run_camera_diagnostic(registry, _MockRuntime(), _MockSolver(), _mock_ds())
    assert len(reports) == 2
    assert all(r.status == CameraDiagnosticStatus.SOLVED for r in reports)


def test_min_stars_constant():
    assert MIN_STARS_BEFORE_SOLVE == 15
