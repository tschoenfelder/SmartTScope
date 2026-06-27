"""Unit tests for GET /api/logs (M8-014 / REQ-LOG-001)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from smart_telescope.app import app
from smart_telescope.api import deps
from smart_telescope.services.section_logger import LOG_SECTIONS, SectionLogger

_SESSION = "test0000-0000-0000-0000-000000000001"


def _inject(svc: SectionLogger) -> TestClient:
    app.dependency_overrides[deps.get_section_logger] = lambda: svc
    client = TestClient(app, raise_server_exceptions=True)
    return client


def _cleanup():
    app.dependency_overrides.pop(deps.get_section_logger, None)


class TestListLogPaths:
    def teardown_method(self, _):
        _cleanup()

    def test_returns_200(self):
        client = _inject(SectionLogger(session_id=_SESSION))
        r = client.get("/api/logs")
        assert r.status_code == 200

    def test_response_has_logs_key(self):
        client = _inject(SectionLogger(session_id=_SESSION))
        data = client.get("/api/logs").json()
        assert "logs" in data

    def test_all_12_sections_present(self):
        client = _inject(SectionLogger(session_id=_SESSION))
        logs = client.get("/api/logs").json()["logs"]
        assert set(logs.keys()) == set(LOG_SECTIONS)

    def test_all_paths_null_without_log_dir(self):
        client = _inject(SectionLogger(session_id=_SESSION))
        logs = client.get("/api/logs").json()["logs"]
        assert all(v is None for v in logs.values())

    def test_paths_set_when_log_dir_configured(self, tmp_path):
        svc = SectionLogger(session_id=_SESSION, log_dir=str(tmp_path))
        client = _inject(svc)
        logs = client.get("/api/logs").json()["logs"]
        assert all(v is not None for v in logs.values())
        svc.close()
