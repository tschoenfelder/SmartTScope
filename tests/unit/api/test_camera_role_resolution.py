"""Tests for POD-010: resolve_camera_index helper in api/deps.py."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from smart_telescope.api import deps
from smart_telescope.api.deps import resolve_camera_index


def _mock_registry(role: str | None, camera_index: int | None) -> MagicMock:
    """Return a mock OpticalTrainRegistry where `role` resolves to camera_index (or None)."""
    reg = MagicMock()
    if camera_index is not None:
        train = MagicMock()
        train.camera_index = camera_index
        reg.by_camera_role.return_value = train
    else:
        reg.by_camera_role.return_value = None
    return reg


class TestResolveCameraIndex:
    def test_no_role_returns_camera_index_unchanged(self) -> None:
        assert resolve_camera_index(3, None) == 3

    def test_empty_string_role_returns_camera_index_unchanged(self) -> None:
        assert resolve_camera_index(2, "") == 2

    def test_valid_role_returns_train_camera_index(self) -> None:
        reg = _mock_registry("main", camera_index=1)
        with patch.object(deps, "get_optical_train_registry", return_value=reg):
            result = resolve_camera_index(0, "main")
        assert result == 1

    def test_valid_role_overrides_camera_index(self) -> None:
        reg = _mock_registry("guide", camera_index=2)
        with patch.object(deps, "get_optical_train_registry", return_value=reg):
            result = resolve_camera_index(99, "guide")
        assert result == 2

    def test_unknown_role_raises_422(self) -> None:
        reg = _mock_registry("nonexistent", camera_index=None)
        with patch.object(deps, "get_optical_train_registry", return_value=reg):
            with pytest.raises(HTTPException) as exc_info:
                resolve_camera_index(0, "nonexistent")
        assert exc_info.value.status_code == 422
        assert "nonexistent" in exc_info.value.detail


import numpy as np
from astropy.io import fits
from fastapi.testclient import TestClient

from smart_telescope.app import app
from smart_telescope.domain.frame import FitsFrame
from smart_telescope.ports.camera import CameraPort
from smart_telescope.ports.solver import SolveResult, SolverPort

client = TestClient(app)

_solver_patches: list = []


def _mock_camera() -> MagicMock:
    cam = MagicMock(spec=CameraPort)
    rng = np.random.default_rng(0)
    pixels = rng.random((32, 32)).astype(np.float32)
    hdr = fits.Header()
    hdr["EXPTIME"] = 1.0
    cam.capture.return_value = FitsFrame(pixels=pixels, header=hdr, exposure_seconds=1.0)
    return cam


def _mock_solver_obj() -> MagicMock:
    s = MagicMock(spec=SolverPort)
    s.solve.return_value = SolveResult(success=True, ra=5.5, dec=-5.4, pa=0.0)
    return s


def _inject_solver(camera: MagicMock, solver: MagicMock) -> None:
    """Inject solver via dependency override; camera via module-level patch
    (solver.py imports get_preview_camera directly, not via deps.*)."""
    app.dependency_overrides[deps.get_solver] = lambda: solver
    p = patch("smart_telescope.api.solver.get_preview_camera", return_value=camera)
    p.start()
    _solver_patches.append(p)


@pytest.fixture(autouse=True)
def _reset_overrides() -> None:  # type: ignore[misc]
    yield
    app.dependency_overrides.clear()
    for p in _solver_patches:
        p.stop()
    _solver_patches.clear()


class TestSolverAcceptsCameraRole:
    def test_camera_role_accepted_returns_200(self) -> None:
        reg = _mock_registry("main", camera_index=0)
        _inject_solver(_mock_camera(), _mock_solver_obj())
        with patch.object(deps, "get_optical_train_registry", return_value=reg):
            r = client.post("/api/solver/solve", json={"camera_role": "main", "exposure": 2.0, "gain": 200})
        assert r.status_code == 200

    def test_unknown_camera_role_returns_422(self) -> None:
        reg = _mock_registry("nope", camera_index=None)
        _inject_solver(_mock_camera(), _mock_solver_obj())
        with patch.object(deps, "get_optical_train_registry", return_value=reg):
            r = client.post("/api/solver/solve", json={"camera_role": "nope", "exposure": 2.0, "gain": 200})
        assert r.status_code == 422

    def test_no_camera_role_falls_back_to_camera_index(self) -> None:
        _inject_solver(_mock_camera(), _mock_solver_obj())
        r = client.post("/api/solver/solve", json={"camera_index": 0, "exposure": 2.0, "gain": 200})
        assert r.status_code == 200


class TestHistogramAcceptsCameraRole:
    # histogram.py calls deps.get_preview_camera(...) — patch.object on deps works here
    def test_camera_role_accepted_returns_200(self) -> None:
        reg = _mock_registry("main", camera_index=0)
        with (
            patch.object(deps, "get_optical_train_registry", return_value=reg),
            patch.object(deps, "get_preview_camera", return_value=_mock_camera()),
        ):
            r = client.post("/api/histogram/analyze", params={
                "camera_role": "main", "exposure": 2.0, "gain": 200,
            })
        assert r.status_code == 200

    def test_unknown_camera_role_returns_422(self) -> None:
        reg = _mock_registry("nope", camera_index=None)
        with patch.object(deps, "get_optical_train_registry", return_value=reg):
            r = client.post("/api/histogram/analyze", params={
                "camera_role": "nope", "exposure": 2.0, "gain": 200,
            })
        assert r.status_code == 422

    def test_no_camera_role_falls_back_to_camera_index(self) -> None:
        with patch.object(deps, "get_preview_camera", return_value=_mock_camera()):
            r = client.post("/api/histogram/analyze", params={
                "camera_index": 0, "exposure": 2.0, "gain": 200,
            })
        assert r.status_code == 200
