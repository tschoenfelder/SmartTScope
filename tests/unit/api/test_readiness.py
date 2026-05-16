"""Unit tests for GET /api/readiness and ReadinessService."""

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from smart_telescope.app import app
from smart_telescope.services.readiness import Level, ReadinessService

client = TestClient(app)


# ── helpers ───────────────────────────────────────────────────────────────────

def _patch_all_green(tmp_path: Path) -> dict:
    """Return a patch.multiple kwargs dict that makes every check pass."""
    stars = tmp_path / "stars.cfg"
    stars.write_text("# stars")
    horizon = tmp_path / "horizon.dat"
    horizon.write_text("# horizon")
    storage = tmp_path / "astro"
    storage.mkdir()
    astap = tmp_path / "astap"
    catalog = tmp_path / "catalog.290"
    catalog.write_bytes(b"")
    return dict(
        stars_cfg=str(stars),
        horizon_dat=str(horizon),
        storage_dir=str(storage),
        astap_path=str(astap),
        astap_catalog=str(catalog),
    )


# ── API smoke test ────────────────────────────────────────────────────────────

class TestReadinessEndpoint:
    def test_returns_200(self) -> None:
        resp = client.get("/api/readiness")
        assert resp.status_code == 200

    def test_response_has_required_fields(self) -> None:
        d = client.get("/api/readiness").json()
        assert "overall" in d
        assert "can_observe" in d
        assert "items" in d
        assert "checked_at" in d

    def test_overall_is_valid_level(self) -> None:
        d = client.get("/api/readiness").json()
        assert d["overall"] in ("green", "yellow", "red")

    def test_items_have_required_fields(self) -> None:
        d = client.get("/api/readiness").json()
        for item in d["items"]:
            assert "key" in item
            assert "label" in item
            assert "level" in item
            assert "message" in item


# ── ReadinessService unit tests ───────────────────────────────────────────────

class TestStarsCfgCheck:
    def test_green_when_file_exists(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        p = tmp_path / "stars.cfg"
        p.write_text("# stars")
        monkeypatch.setattr("smart_telescope.config.STARS_CFG", str(p))
        item = ReadinessService()._check_stars_cfg()
        assert item.level == Level.GREEN

    def test_red_when_file_missing(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("smart_telescope.config.STARS_CFG", str(tmp_path / "missing.cfg"))
        item = ReadinessService()._check_stars_cfg()
        assert item.level == Level.RED
        assert item.repair is not None

    def test_red_includes_repair_guidance(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("smart_telescope.config.STARS_CFG", str(tmp_path / "missing.cfg"))
        item = ReadinessService()._check_stars_cfg()
        assert "config.toml" in (item.repair or "")


class TestHorizonDatCheck:
    def test_green_when_file_exists(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        p = tmp_path / "horizon.dat"
        p.write_text("# horizon")
        monkeypatch.setattr("smart_telescope.config.HORIZON_DAT", str(p))
        item = ReadinessService()._check_horizon_dat()
        assert item.level == Level.GREEN

    def test_yellow_when_file_missing(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("smart_telescope.config.HORIZON_DAT", str(tmp_path / "missing.dat"))
        item = ReadinessService()._check_horizon_dat()
        assert item.level == Level.YELLOW

    def test_yellow_does_not_block_observation(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("smart_telescope.config.HORIZON_DAT", str(tmp_path / "missing.dat"))
        svc = ReadinessService()
        items = [svc._check_horizon_dat()]
        assert all(i.level != Level.RED for i in items)


class TestStorageCheck:
    def test_green_when_dir_exists_and_writable(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("smart_telescope.config.STORAGE_DIR", str(tmp_path))
        item = ReadinessService()._check_storage()
        assert item.level in (Level.GREEN, Level.YELLOW)  # yellow if low space

    def test_yellow_when_not_configured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("smart_telescope.config.STORAGE_DIR", "")
        item = ReadinessService()._check_storage()
        assert item.level == Level.YELLOW

    def test_red_when_dir_missing(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("smart_telescope.config.STORAGE_DIR", str(tmp_path / "nonexistent"))
        item = ReadinessService()._check_storage()
        assert item.level == Level.RED
        assert item.repair is not None


class TestAstapCheck:
    def test_red_when_astap_not_found(self) -> None:
        with patch("smart_telescope.services.readiness.ReadinessService._check_astap") as m:
            from smart_telescope.services.readiness import ReadinessItem
            m.return_value = [
                ReadinessItem(key="astap_exe", label="ASTAP", level=Level.RED, message="not found"),
                ReadinessItem(key="astap_catalog", label="Catalog", level=Level.RED, message="cannot check"),
            ]
            items = ReadinessService()._check_astap()
            # just ensure the method returns a list of 2 items in real code
        with patch("smart_telescope.adapters.astap.solver.find_astap", return_value=None):
            items = ReadinessService()._check_astap()
        assert len(items) == 2
        assert all(i.level == Level.RED for i in items)

    def test_green_when_both_found(self, tmp_path: Path) -> None:
        astap = tmp_path / "astap"
        catalog = tmp_path / "catalog.290"
        catalog.write_bytes(b"")
        with (
            patch("smart_telescope.adapters.astap.solver.find_astap", return_value=astap),
            patch("smart_telescope.adapters.astap.solver.find_catalog", return_value=catalog),
        ):
            items = ReadinessService()._check_astap()
        assert all(i.level == Level.GREEN for i in items)

    def test_red_catalog_when_exe_found_but_no_catalog(self, tmp_path: Path) -> None:
        astap = tmp_path / "astap"
        with (
            patch("smart_telescope.adapters.astap.solver.find_astap", return_value=astap),
            patch("smart_telescope.adapters.astap.solver.find_catalog", return_value=None),
        ):
            items = ReadinessService()._check_astap()
        assert items[0].level == Level.GREEN   # exe
        assert items[1].level == Level.RED     # catalog


class TestCameraCheck:
    def test_green_when_cameras_configured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("smart_telescope.config.CAMERAS", {"main": 0})
        item = ReadinessService()._check_camera()
        assert item.level == Level.GREEN

    def test_yellow_when_no_cameras(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("smart_telescope.config.CAMERAS", {})
        item = ReadinessService()._check_camera()
        assert item.level == Level.YELLOW


class TestMountFocuserCheck:
    def test_yellow_when_no_onstep_port(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("smart_telescope.config.ONSTEP_PORT", "")
        monkeypatch.delenv("ONSTEP_PORT", raising=False)
        items = ReadinessService()._check_mount_focuser()
        assert len(items) == 2
        assert all(i.level == Level.YELLOW for i in items)

    def test_yellow_when_port_configured_but_not_connected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("smart_telescope.config.ONSTEP_PORT", "/dev/ttyUSB0")
        monkeypatch.delenv("ONSTEP_PORT", raising=False)
        # Runtime not yet built (adapters_built=False) → yellow "not yet connected"
        items = ReadinessService()._check_mount_focuser()
        assert len(items) == 2
        assert all(i.level == Level.YELLOW for i in items)


class TestOverallLevel:
    def test_red_overall_if_any_red_item(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("smart_telescope.config.STARS_CFG", str(tmp_path / "missing.cfg"))
        report = ReadinessService().check()
        assert report.overall == Level.RED
        assert report.can_observe is False

    def test_yellow_overall_if_no_red_but_some_yellow(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        stars = tmp_path / "stars.cfg"
        stars.write_text("# stars")
        monkeypatch.setattr("smart_telescope.config.STARS_CFG", str(stars))
        monkeypatch.setattr("smart_telescope.config.HORIZON_DAT", str(tmp_path / "missing.dat"))
        monkeypatch.setattr("smart_telescope.config.STORAGE_DIR", "")
        monkeypatch.setattr("smart_telescope.config.CAMERAS", {})
        monkeypatch.setattr("smart_telescope.config.ONSTEP_PORT", "")
        monkeypatch.delenv("ONSTEP_PORT", raising=False)
        with (
            patch("smart_telescope.adapters.astap.solver.find_astap", return_value=tmp_path / "astap"),
            patch("smart_telescope.adapters.astap.solver.find_catalog", return_value=tmp_path / "cat.290"),
        ):
            report = ReadinessService().check()
        assert report.overall == Level.YELLOW
        assert report.can_observe is True
