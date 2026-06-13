"""Tests for camera_config_suggestion domain module (CID-007)."""
from __future__ import annotations

import sys

import pytest

from smart_telescope.domain.camera_config_suggestion import (
    ROLE_PRIORITY,
    _default_capture_mode,
    _default_offset,
    generate_toml_snippet,
    suggest_role,
)


# ── suggest_role ─────────────────────────────────────────────────────────────

class TestSuggestRole:
    def test_empty_existing_returns_main(self):
        assert suggest_role("ATR585M", set()) == "main"

    def test_main_taken_returns_guide(self):
        assert suggest_role("GPCMOS02000KPA", {"main"}) == "guide"

    def test_main_and_guide_taken_returns_oag(self):
        assert suggest_role("G3M678M", {"main", "guide"}) == "oag"

    def test_all_priority_roles_taken_returns_camera2(self):
        assert suggest_role("SomeCamera", {"main", "guide", "oag"}) == "camera2"

    def test_camera2_taken_returns_camera3(self):
        assert suggest_role("X", {"main", "guide", "oag", "camera2"}) == "camera3"

    def test_camera3_taken_returns_camera4(self):
        assert suggest_role("X", {"main", "guide", "oag", "camera2", "camera3"}) == "camera4"

    def test_model_name_not_used_for_role(self):
        # model_name is not used to derive the role — role comes from existing set
        assert suggest_role("guide_cam", set()) == "main"

    def test_role_priority_order(self):
        assert ROLE_PRIORITY == ["main", "guide", "oag"]


# ── _default_offset ───────────────────────────────────────────────────────────

class TestDefaultOffset:
    def test_gpcmos_returns_10(self):
        assert _default_offset("GPCMOS02000KPA") == 10

    def test_gpcmos_lowercase_returns_10(self):
        assert _default_offset("gpcmos02000kpa") == 10

    def test_atr585m_returns_150(self):
        assert _default_offset("ATR585M") == 150

    def test_g3m678m_returns_150(self):
        assert _default_offset("G3M678M") == 150

    def test_unknown_model_returns_150(self):
        assert _default_offset("UnknownCam") == 150


# ── _default_capture_mode ─────────────────────────────────────────────────────

class TestDefaultCaptureMode:
    def test_mono_tec_returns_stream(self):
        assert _default_capture_mode(has_mono=True, has_tec=True) == "indi-stream-trigger"

    def test_mono_no_tec_returns_snap(self):
        assert _default_capture_mode(has_mono=True, has_tec=False) == "snap"

    def test_colour_tec_returns_snap(self):
        assert _default_capture_mode(has_mono=False, has_tec=True) == "snap"

    def test_colour_no_tec_returns_snap(self):
        assert _default_capture_mode(has_mono=False, has_tec=False) == "snap"


# ── generate_toml_snippet ─────────────────────────────────────────────────────

class TestGenerateTomlSnippet:
    def _make(self, **kwargs):
        defaults = dict(
            model_name="ATR585M",
            cam_id="tp-4-1-10-0547-157c",
            has_tec=True,
            has_mono=True,
            suggested_role="main",
            first_telescope="c8",
        )
        defaults.update(kwargs)
        return generate_toml_snippet(**defaults)

    def test_snippet_contains_model_name(self):
        s = self._make()
        assert "ATR585M" in s

    def test_snippet_contains_camera_id(self):
        s = self._make()
        assert "tp-4-1-10-0547-157c" in s

    def test_snippet_contains_cameras_section(self):
        s = self._make(suggested_role="main")
        assert "[cameras.main]" in s

    def test_snippet_contains_optical_trains_section(self):
        s = self._make(suggested_role="main")
        assert "[optical_trains.main]" in s

    def test_snippet_references_suggested_role(self):
        s = self._make(suggested_role="guide")
        assert "[cameras.guide]" in s
        assert "[optical_trains.guide]" in s

    def test_snippet_uses_first_telescope(self):
        s = self._make(first_telescope="guide_scope")
        assert "guide_scope" in s

    def test_snippet_uses_c8_fallback_when_no_telescope(self):
        s = self._make(first_telescope=None)
        assert '"c8"' in s

    def test_snippet_is_valid_toml(self):
        if sys.version_info < (3, 11):
            tomllib = pytest.importorskip("tomli")
        else:
            import tomllib
        s = self._make()
        # Strip comment lines before parsing (TOML parser handles # comments fine)
        parsed = tomllib.loads(s)
        assert "cameras" in parsed

    def test_mono_tec_uses_stream_mode(self):
        s = self._make(has_mono=True, has_tec=True)
        assert "indi-stream-trigger" in s

    def test_guide_cam_uses_snap_mode(self):
        s = self._make(model_name="GPCMOS02000KPA", has_mono=True, has_tec=False,
                       suggested_role="guide")
        assert "snap" in s

    def test_guide_cam_offset_is_10(self):
        s = self._make(model_name="GPCMOS02000KPA", has_mono=True, has_tec=False)
        assert "offset_lcg   = 10" in s

    def test_imaging_cam_offset_is_150(self):
        s = self._make(model_name="ATR585M", has_tec=True)
        assert "offset_lcg   = 150" in s

    def test_snippet_contains_focuser_hint(self):
        s = self._make(has_mono=True, has_tec=True)
        assert "focuser" in s
