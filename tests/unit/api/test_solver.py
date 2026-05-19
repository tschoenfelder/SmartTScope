"""Unit tests for GET /api/solver/status and POST /api/solver/solve."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from astropy.io import fits
from fastapi.testclient import TestClient

from smart_telescope.api import deps
from smart_telescope.app import app
from smart_telescope.domain.frame import FitsFrame
from smart_telescope.ports.camera import CameraPort
from smart_telescope.ports.solver import SolveResult, SolverPort

_active_patches: list = []

client = TestClient(app)


def _mock_camera() -> MagicMock:
    c = MagicMock(spec=CameraPort)
    rng = np.random.default_rng(0)
    pixels = rng.random((32, 32)).astype(np.float32)
    hdr = fits.Header()
    hdr["EXPTIME"] = 1.0
    c.capture.return_value = FitsFrame(pixels=pixels, header=hdr, exposure_seconds=1.0)
    return c


def _mock_solver(success: bool = True) -> MagicMock:
    s = MagicMock(spec=SolverPort)
    s.solve.return_value = (
        SolveResult(success=True, ra=5.5881, dec=-5.391, pa=0.0)
        if success
        else SolveResult(success=False, error="no stars found")
    )
    return s


@pytest.fixture(autouse=True)
def _reset() -> None:
    deps.reset()
    yield
    app.dependency_overrides.clear()
    deps.reset()
    for p in _active_patches:
        p.stop()
    _active_patches.clear()


def _inject(solver: MagicMock, camera: MagicMock | None = None) -> None:
    app.dependency_overrides[deps.get_solver] = lambda: solver
    if camera is not None:
        # get_preview_camera is called directly (not via Depends) — must use patch
        p = patch("smart_telescope.api.solver.get_preview_camera", return_value=camera)
        p.start()
        _active_patches.append(p)


def _patch_solver(astap: str | None, catalog: Path | None):
    return patch.multiple(
        "smart_telescope.api.solver",
        _find_astap=lambda: astap,
        _find_catalog=lambda exe: catalog,
    )


class TestSolverStatus:
    def test_returns_200(self) -> None:
        assert client.get("/api/solver/status").status_code == 200

    def test_ready_false_when_astap_missing(self) -> None:
        with _patch_solver(None, None):
            body = client.get("/api/solver/status").json()
        assert body["ready"] is False

    def test_ready_false_when_catalog_missing(self, tmp_path: Path) -> None:
        with _patch_solver("/usr/bin/astap", None):
            body = client.get("/api/solver/status").json()
        assert body["ready"] is False

    def test_ready_true_when_both_found(self, tmp_path: Path) -> None:
        with _patch_solver("/usr/bin/astap", tmp_path):
            body = client.get("/api/solver/status").json()
        assert body["ready"] is True

    def test_astap_null_when_not_found(self) -> None:
        with _patch_solver(None, None):
            body = client.get("/api/solver/status").json()
        assert body["astap"] is None

    def test_astap_path_when_found(self) -> None:
        with _patch_solver("/usr/bin/astap", None):
            body = client.get("/api/solver/status").json()
        assert body["astap"] == "/usr/bin/astap"

    def test_catalog_null_when_not_found(self) -> None:
        with _patch_solver("/usr/bin/astap", None):
            body = client.get("/api/solver/status").json()
        assert body["catalog"] is None

    def test_catalog_path_when_found(self, tmp_path: Path) -> None:
        with _patch_solver("/usr/bin/astap", tmp_path):
            body = client.get("/api/solver/status").json()
        assert body["catalog"] == str(tmp_path)


# ── POST /api/solver/solve ────────────────────────────────────────────────────


class TestSolverSolve:
    def test_returns_200_on_success(self) -> None:
        _inject(_mock_solver(), _mock_camera())
        assert client.post("/api/solver/solve", json={}).status_code == 200

    def test_success_true_and_coords_present(self) -> None:
        _inject(_mock_solver(), _mock_camera())
        data = client.post("/api/solver/solve", json={}).json()
        assert data["success"] is True
        assert abs(data["ra"] - 5.5881) < 0.001
        assert abs(data["dec"] - -5.391) < 0.001

    def test_pa_field_present(self) -> None:
        _inject(_mock_solver(), _mock_camera())
        data = client.post("/api/solver/solve", json={}).json()
        assert "pa" in data

    def test_solve_time_is_nonnegative(self) -> None:
        _inject(_mock_solver(), _mock_camera())
        data = client.post("/api/solver/solve", json={}).json()
        assert data["solve_time_s"] >= 0.0

    def test_success_false_when_solver_fails(self) -> None:
        _inject(_mock_solver(success=False), _mock_camera())
        data = client.post("/api/solver/solve", json={}).json()
        assert data["success"] is False
        assert data["error"] == "no stars found"

    def test_camera_capture_called_with_exposure(self) -> None:
        cam = _mock_camera()
        _inject(_mock_solver(), cam)
        client.post("/api/solver/solve", json={"exposure": 10.0})
        cam.capture.assert_called_once_with(10.0)

    def test_solver_called_with_pixel_scale(self) -> None:
        sol = _mock_solver()
        _inject(sol, _mock_camera())
        client.post("/api/solver/solve", json={"pixel_scale": 0.60})
        args = sol.solve.call_args
        assert abs(args[0][1] - 0.60) < 1e-6

    def test_returns_422_on_zero_exposure(self) -> None:
        _inject(_mock_solver(), _mock_camera())
        assert client.post("/api/solver/solve", json={"exposure": 0}).status_code == 422

    def test_defaults_accepted(self) -> None:
        _inject(_mock_solver(), _mock_camera())
        assert client.post("/api/solver/solve", json={}).status_code == 200
