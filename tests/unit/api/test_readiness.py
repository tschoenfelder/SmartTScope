"""Unit tests for GET /api/readiness and ReadinessService."""

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import smart_telescope.config as _config_mod
from smart_telescope.app import app
from smart_telescope.config import ConfigError, _expand, check_load_error
from smart_telescope.services.readiness import Level, ReadinessItem, ReadinessService

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
        assert "can_preview" in d
        assert "can_goto" in d
        assert "can_solve" in d
        assert "can_autofocus" in d
        assert "can_save" in d
        assert "mode" in d
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


# ── R5-003: ConfigError replaces sys.exit ─────────────────────────────────────

class TestConfigError:
    """R5-001..003: ConfigError is raised by check_load_error; not sys.exit."""

    def test_check_load_error_is_noop_when_no_error(self) -> None:
        with patch.object(_config_mod, "_load_error", None):
            check_load_error()  # must not raise

    def test_check_load_error_raises_config_error(self) -> None:
        err = ConfigError("Config parse error in /path/config.toml: ...")
        with patch.object(_config_mod, "_load_error", err):
            with pytest.raises(ConfigError, match="parse error"):
                check_load_error()

    def test_readiness_shows_red_on_parse_error(self) -> None:
        err = ConfigError("Config parse error in /some/config.toml: invalid TOML")
        with patch.object(_config_mod, "_load_error", err):
            item = ReadinessService()._check_config_file()
        assert item.level == Level.RED
        assert "parse error" in item.message.lower()
        assert item.repair is not None

    def test_readiness_overall_red_on_config_parse_error(self) -> None:
        err = ConfigError("Config parse error in /some/config.toml: invalid TOML")
        with patch.object(_config_mod, "_load_error", err):
            report = ReadinessService().check()
        assert report.overall == Level.RED
        assert report.can_observe is False
        config_item = next(i for i in report.items if i.key == "config_file")
        assert config_item.level == Level.RED


# ── BUG-008: tilde path expansion in config ───────────────────────────────────

class TestExpandPath:
    """BUG-008: _expand() correctly resolves tilde paths (fixed by R5-004)."""

    def test_tilde_expanded_to_home(self) -> None:
        result = _expand("~/stars.cfg")
        assert "~" not in result
        assert result.endswith("stars.cfg")
        assert Path(result).is_absolute()

    def test_empty_string_returns_empty(self) -> None:
        assert _expand("") == ""

    def test_absolute_path_unchanged(self, tmp_path: Path) -> None:
        p = str(tmp_path / "stars.cfg")
        assert _expand(p) == p

    def test_stars_cfg_config_value_is_already_expanded(self) -> None:
        assert "~" not in _config_mod.STARS_CFG


# ── Overall level tests ───────────────────────────────────────────────────────

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
            patch.object(ReadinessService, "_get_hardware_mode", return_value="real"),
        ):
            report = ReadinessService().check()
        assert report.overall == Level.YELLOW
        assert report.can_observe is True


# ── R5-011: hardware mode field ───────────────────────────────────────────────

class TestHardwareMode:
    """R5-011: mode field in ReadinessReport; can_observe blocked for non-real modes."""

    def test_mode_field_present_in_api_response(self) -> None:
        d = client.get("/api/readiness").json()
        assert "mode" in d
        assert d["mode"] in ("real", "simulator", "mock")

    def test_mode_real_allows_observe_when_no_red_items(self, tmp_path: Path) -> None:
        stars = tmp_path / "stars.cfg"
        stars.write_text("# stars")
        with (
            patch.object(ReadinessService, "_get_hardware_mode", return_value="real"),
            patch("smart_telescope.config.STARS_CFG", str(stars)),
            patch("smart_telescope.config.HORIZON_DAT", str(stars)),
            patch("smart_telescope.config.STORAGE_DIR", str(tmp_path)),
            patch("smart_telescope.config.CAMERAS", {"main": 0}),
            patch("smart_telescope.config.ONSTEP_PORT", ""),
            patch.dict("os.environ", {}, clear=False),
            patch("smart_telescope.adapters.astap.solver.find_astap", return_value=tmp_path / "astap"),
            patch("smart_telescope.adapters.astap.solver.find_catalog", return_value=tmp_path / "cat.290"),
        ):
            report = ReadinessService().check()
        assert report.mode == "real"
        assert report.can_observe is True

    def test_mode_mock_blocks_can_observe(self) -> None:
        with patch.object(ReadinessService, "_get_hardware_mode", return_value="mock"):
            report = ReadinessService().check()
        assert report.mode == "mock"
        assert report.can_observe is False

    def test_mode_simulator_blocks_can_observe(self, tmp_path: Path) -> None:
        stars = tmp_path / "stars.cfg"
        stars.write_text("# stars")
        with (
            patch.object(ReadinessService, "_get_hardware_mode", return_value="simulator"),
            patch("smart_telescope.adapters.astap.solver.find_astap", return_value=tmp_path / "astap"),
            patch("smart_telescope.adapters.astap.solver.find_catalog", return_value=tmp_path / "cat.290"),
        ):
            report = ReadinessService().check()
        assert report.mode == "simulator"
        assert report.can_observe is False

    def test_mode_item_in_items_list(self) -> None:
        with patch.object(ReadinessService, "_get_hardware_mode", return_value="real"):
            report = ReadinessService().check()
        mode_item = next((i for i in report.items if i.key == "hardware_mode"), None)
        assert mode_item is not None
        assert "REAL" in mode_item.message

    def test_mode_mock_item_has_repair_guidance(self) -> None:
        with patch.object(ReadinessService, "_get_hardware_mode", return_value="mock"):
            report = ReadinessService().check()
        mode_item = next(i for i in report.items if i.key == "hardware_mode")
        assert mode_item.repair is not None
        assert "config.toml" in mode_item.repair

    def test_runtime_hardware_mode_default_is_mock(self) -> None:
        from smart_telescope.runtime import RuntimeContext
        ctx = RuntimeContext()
        assert ctx.hardware_mode == "mock"

    def test_runtime_hardware_mode_reset_to_mock(self) -> None:
        from smart_telescope.runtime import get_runtime
        rt = get_runtime()
        rt._hardware_mode = "real"
        rt.reset_for_tests()
        assert rt.hardware_mode == "mock"


class TestCapabilityFlags:
    def _item(self, key: str, level: Level) -> ReadinessItem:
        return ReadinessItem(key=key, label=key, level=level, message="")

    def test_all_flags_true_when_no_red_items(self) -> None:
        items = [
            self._item("camera", Level.GREEN),
            self._item("mount", Level.GREEN),
            self._item("astap_exe", Level.GREEN),
            self._item("astap_catalog", Level.GREEN),
            self._item("focuser", Level.GREEN),
            self._item("storage", Level.GREEN),
        ]
        flags = ReadinessService._capability_flags(items)
        assert flags["can_preview"] is True
        assert flags["can_goto"] is True
        assert flags["can_solve"] is True
        assert flags["can_autofocus"] is True
        assert flags["can_save"] is True

    def test_camera_red_blocks_preview_not_goto(self) -> None:
        flags = ReadinessService._capability_flags([self._item("camera", Level.RED)])
        assert flags["can_preview"] is False
        assert flags["can_goto"] is True

    def test_mount_red_blocks_goto_not_preview(self) -> None:
        flags = ReadinessService._capability_flags([self._item("mount", Level.RED)])
        assert flags["can_goto"] is False
        assert flags["can_preview"] is True

    def test_astap_exe_red_blocks_solve(self) -> None:
        flags = ReadinessService._capability_flags([self._item("astap_exe", Level.RED)])
        assert flags["can_solve"] is False

    def test_astap_catalog_red_blocks_solve(self) -> None:
        flags = ReadinessService._capability_flags([self._item("astap_catalog", Level.RED)])
        assert flags["can_solve"] is False

    def test_focuser_yellow_does_not_block_autofocus(self) -> None:
        flags = ReadinessService._capability_flags([self._item("focuser", Level.YELLOW)])
        assert flags["can_autofocus"] is True

    def test_focuser_red_blocks_autofocus(self) -> None:
        flags = ReadinessService._capability_flags([self._item("focuser", Level.RED)])
        assert flags["can_autofocus"] is False

    def test_storage_red_blocks_save(self) -> None:
        flags = ReadinessService._capability_flags([self._item("storage", Level.RED)])
        assert flags["can_save"] is False

    def test_storage_yellow_does_not_block_save(self) -> None:
        flags = ReadinessService._capability_flags([self._item("storage", Level.YELLOW)])
        assert flags["can_save"] is True

    def test_astap_missing_blocks_solve_only(self) -> None:
        items = [
            self._item("astap_exe", Level.RED),
            self._item("astap_catalog", Level.RED),
            self._item("camera", Level.GREEN),
            self._item("mount", Level.GREEN),
        ]
        flags = ReadinessService._capability_flags(items)
        assert flags["can_solve"] is False
        assert flags["can_preview"] is True
        assert flags["can_goto"] is True

    def test_mount_fail_allows_camera_preview(self) -> None:
        items = [self._item("mount", Level.RED), self._item("camera", Level.GREEN)]
        flags = ReadinessService._capability_flags(items)
        assert flags["can_goto"] is False
        assert flags["can_preview"] is True

    def test_camera_fail_allows_mount_controls(self) -> None:
        items = [self._item("camera", Level.RED), self._item("mount", Level.GREEN)]
        flags = ReadinessService._capability_flags(items)
        assert flags["can_preview"] is False
        assert flags["can_goto"] is True
