"""Unit tests for GET /api/solver/status."""
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from smart_telescope.app import app

client = TestClient(app)


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
