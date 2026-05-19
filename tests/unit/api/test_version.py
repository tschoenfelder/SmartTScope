"""Unit tests for GET /api/version."""
from unittest.mock import patch

from fastapi.testclient import TestClient

from smart_telescope.app import app

client = TestClient(app)


class TestVersionEndpoint:
    def test_returns_200(self) -> None:
        assert client.get("/api/version").status_code == 200

    def test_response_has_version_field(self) -> None:
        data = client.get("/api/version").json()
        assert "version" in data
        assert data["version"] == "0.1.0"

    def test_response_has_git_hash_field(self) -> None:
        data = client.get("/api/version").json()
        assert "git_hash" in data

    def test_git_hash_is_string(self) -> None:
        data = client.get("/api/version").json()
        assert isinstance(data["git_hash"], str)

    def test_git_hash_empty_when_subprocess_fails(self) -> None:
        with patch("smart_telescope.api.version._git_hash", return_value=""):
            data = client.get("/api/version").json()
        assert data["git_hash"] == ""

    def test_git_hash_returned_when_available(self) -> None:
        with patch("smart_telescope.api.version._git_hash", return_value="abc1234"):
            data = client.get("/api/version").json()
        assert data["git_hash"] == "abc1234"
