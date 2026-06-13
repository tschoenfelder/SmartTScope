"""Tests for CID-007 — detect newly connected cameras not in config."""
from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from smart_telescope.api.cameras import _do_scan, invalidate_camera_scan
from smart_telescope.services.readiness import Level, ReadinessService


# ── SDK stub helpers (shared with test_cameras.py) ────────────────────────────

def _make_model(
    name: str = "TestCam",
    flag: int = 0,
    xpixsz: float = 3.76,
    ypixsz: float = 3.76,
) -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        flag=flag,
        maxspeed=2,
        preview=2,
        still=1,
        xpixsz=xpixsz,
        ypixsz=ypixsz,
        res=[SimpleNamespace(width=1920, height=1080)],
    )


def _make_device(
    displayname: str = "TestCam",
    cam_id: str = "CAMID-001",
    model: SimpleNamespace | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        displayname=displayname,
        id=cam_id,
        model=model or _make_model(displayname),
    )


def _make_toupcam_mock(devices: list[SimpleNamespace]) -> object:
    class _TC:
        @staticmethod
        def EnumV2():
            return devices
    class _Mod:
        Toupcam = _TC
    return _Mod()


# ── _do_scan: toml_snippet generation ────────────────────────────────────────

class TestDoScanTomlSnippet:
    def setup_method(self):
        invalidate_camera_scan()

    def _scan_with(self, devices, cameras_cfg=None, camera_specs_cfg=None, telescopes_cfg=None):
        """Run _do_scan() with mocked SDK and optional config overrides."""
        import smart_telescope.config as cfg
        cameras_patch = cameras_cfg if cameras_cfg is not None else {}
        specs_patch = camera_specs_cfg if camera_specs_cfg is not None else {}
        telescopes_patch = telescopes_cfg if telescopes_cfg is not None else {}
        with patch.dict(sys.modules, {"toupcam": _make_toupcam_mock(devices)}), \
             patch.object(cfg, "CAMERAS", cameras_patch), \
             patch.object(cfg, "CAMERA_SPECS", specs_patch), \
             patch.object(cfg, "TELESCOPES", telescopes_patch):
            return _do_scan()

    def test_unconfigured_camera_gets_snippet(self):
        dev = _make_device("NewCam", "ID-NEW")
        result = self._scan_with([dev])
        cam = result.cameras[0]
        assert cam.role is None
        assert cam.toml_snippet is not None
        assert "[cameras." in cam.toml_snippet

    def test_configured_camera_has_no_snippet(self):
        dev = _make_device("KnownCam", "ID-KNOWN")
        # Configure camera at index 0 as "main"
        result = self._scan_with([dev], cameras_cfg={"main": 0})
        cam = result.cameras[0]
        assert cam.role == "main"
        assert cam.toml_snippet is None

    def test_snippet_contains_model_and_id(self):
        dev = _make_device("ATR585M", "tp-4-1-10-0547-157c")
        result = self._scan_with([dev])
        snippet = result.cameras[0].toml_snippet
        assert "ATR585M" in snippet
        assert "tp-4-1-10-0547-157c" in snippet

    def test_snippet_uses_telescope_from_config(self):
        from smart_telescope.config import TelescopeSpec
        dev = _make_device("NewCam", "NEWID")
        tel = SimpleNamespace(name="guide_scope", aperture_mm=50.0, focal_mm=180.0,
                              type="refractor", obstruction=0.0)
        result = self._scan_with([dev], telescopes_cfg={"guide_scope": tel})
        assert "guide_scope" in result.cameras[0].toml_snippet

    def test_mixed_one_configured_one_not(self):
        dev_known = _make_device("KnownCam", "ID-K")
        dev_new   = _make_device("NewCam",   "ID-N")
        result = self._scan_with([dev_known, dev_new], cameras_cfg={"main": 0})
        cams = {c.display_name: c for c in result.cameras}
        assert cams["KnownCam"].role == "main"
        assert cams["KnownCam"].toml_snippet is None
        assert cams["NewCam"].role is None
        assert cams["NewCam"].toml_snippet is not None

    def test_camera_matched_by_model_spec_has_no_snippet(self):
        """Camera matched via CAMERA_SPECS model substring should not get a snippet."""
        from smart_telescope.config import CameraSpec
        dev = _make_device("ATR585M", "tp-MATCHED")
        spec = CameraSpec(role="main", model="ATR585M")
        result = self._scan_with([dev], camera_specs_cfg={"main": spec})
        assert result.cameras[0].role == "main"
        assert result.cameras[0].toml_snippet is None

    def test_camera_matched_by_camera_id_spec_has_no_snippet(self):
        from smart_telescope.config import CameraSpec
        dev = _make_device("SomeModel", "EXACT-ID-123")
        spec = CameraSpec(role="guide", camera_id="EXACT-ID-123")
        result = self._scan_with([dev], camera_specs_cfg={"guide": spec})
        assert result.cameras[0].role == "guide"
        assert result.cameras[0].toml_snippet is None


# ── ReadinessService._check_unconfigured_cameras ──────────────────────────────

class TestCheckUnconfiguredCameras:
    def _run(self, devices, cameras_cfg=None, camera_specs_cfg=None):
        import smart_telescope.config as cfg
        cameras_patch = cameras_cfg if cameras_cfg is not None else {}
        specs_patch = camera_specs_cfg if camera_specs_cfg is not None else {}
        svc = ReadinessService()
        with patch.dict(sys.modules, {"toupcam": _make_toupcam_mock(devices)}), \
             patch.object(cfg, "CAMERAS", cameras_patch), \
             patch.object(cfg, "CAMERA_SPECS", specs_patch):
            return svc._check_unconfigured_cameras()

    def test_returns_none_when_no_devices(self):
        assert self._run([]) is None

    def test_returns_yellow_for_one_unconfigured_camera(self):
        dev = _make_device("NewCam", "ID-N")
        item = self._run([dev])
        assert item is not None
        assert item.level == Level.YELLOW
        assert item.key == "unconfigured_cameras"
        assert "NewCam" in item.message

    def test_returns_none_when_all_configured_by_index(self):
        dev = _make_device("MyCam", "ID-M")
        item = self._run([dev], cameras_cfg={"main": 0})
        assert item is None

    def test_returns_none_when_matched_by_model_spec(self):
        from smart_telescope.config import CameraSpec
        dev = _make_device("ATR585M", "ID-A")
        spec = CameraSpec(role="main", model="ATR585M")
        item = self._run([dev], camera_specs_cfg={"main": spec})
        assert item is None

    def test_returns_none_when_sdk_unavailable(self):
        svc = ReadinessService()
        with patch.dict(sys.modules, {"toupcam": None}):
            result = svc._check_unconfigured_cameras()
        assert result is None

    def test_message_includes_count(self):
        devs = [_make_device("CamA", "IDA"), _make_device("CamB", "IDB")]
        item = self._run(devs)
        assert item is not None
        assert "2 camera" in item.message

    def test_repair_hints_camera_scan(self):
        dev = _make_device("NewCam", "ID-N")
        item = self._run([dev])
        assert item is not None
        assert "Camera Scan" in item.repair

    def test_check_full_includes_unconfigured_item(self):
        """ReadinessService.check() surfaces unconfigured-camera YELLOW."""
        dev = _make_device("UnknownCam", "ID-UNK")
        import smart_telescope.config as cfg
        svc = ReadinessService()
        with patch.dict(sys.modules, {"toupcam": _make_toupcam_mock([dev])}), \
             patch.object(cfg, "CAMERAS", {}), \
             patch.object(cfg, "CAMERA_SPECS", {}):
            report = svc.check()
        keys = [i.key for i in report.items]
        assert "unconfigured_cameras" in keys
