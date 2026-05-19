"""Unit tests for storage_config and session_folder domain modules."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from smart_telescope.domain.session_folder import make_session_path, sanitize_target_name
from smart_telescope.domain.storage_config import resolve_app_state_dir


# ── sanitize_target_name ──────────────────────────────────────────────────────

class TestSanitizeTargetName:
    def test_simple_name_unchanged(self) -> None:
        assert sanitize_target_name("M42") == "M42"

    def test_space_to_underscore(self) -> None:
        assert sanitize_target_name("NGC 1234") == "NGC_1234"

    def test_multiple_spaces_collapsed(self) -> None:
        assert sanitize_target_name("NGC  1234") == "NGC_1234"

    def test_parens_and_special_chars(self) -> None:
        assert sanitize_target_name("Andromeda (M31)") == "Andromeda_M31"

    def test_leading_trailing_underscores_stripped(self) -> None:
        assert sanitize_target_name("  /bad\\name:  ") == "bad_name"

    def test_colon_removed(self) -> None:
        assert sanitize_target_name("IC:434") == "IC_434"

    def test_forward_slash_removed(self) -> None:
        assert sanitize_target_name("North/South") == "North_South"

    def test_backslash_removed(self) -> None:
        assert sanitize_target_name("East\\West") == "East_West"

    def test_question_mark_removed(self) -> None:
        assert sanitize_target_name("Unknown?") == "Unknown"

    def test_asterisk_removed(self) -> None:
        assert sanitize_target_name("Star*Cloud") == "Star_Cloud"

    def test_mixed_punctuation(self) -> None:
        result = sanitize_target_name("M31 (Andromeda) - DSO")
        assert "_" in result
        assert "M31" in result
        assert "Andromeda" in result
        assert "DSO" in result

    def test_only_invalid_chars_produces_empty(self) -> None:
        # "/" alone → "" after stripping
        assert sanitize_target_name("///") == ""

    def test_unicode_letters_preserved(self) -> None:
        # Letters outside ASCII are kept (not forbidden)
        name = sanitize_target_name("Orión")
        assert "Ori" in name


# ── make_session_path ─────────────────────────────────────────────────────────

class TestMakeSessionPath:
    _DATE = date(2026, 5, 6)

    def test_basic_target(self, tmp_path: Path) -> None:
        p = make_session_path(tmp_path, "Pleiades", self._DATE)
        assert p.name == "2026-05-06_Pleiades"

    def test_parent_is_image_root(self, tmp_path: Path) -> None:
        p = make_session_path(tmp_path, "M42", self._DATE)
        assert p.parent == tmp_path

    def test_target_with_spaces(self, tmp_path: Path) -> None:
        p = make_session_path(tmp_path, "NGC 1234", self._DATE)
        assert p.name == "2026-05-06_NGC_1234"

    def test_target_with_parens(self, tmp_path: Path) -> None:
        p = make_session_path(tmp_path, "Andromeda (M31)", self._DATE)
        assert "Andromeda" in p.name
        assert "M31" in p.name

    def test_date_format_is_iso(self, tmp_path: Path) -> None:
        p = make_session_path(tmp_path, "Jupiter", date(2026, 1, 3))
        assert p.name.startswith("2026-01-03_")

    def test_uses_today_when_date_not_supplied(self, tmp_path: Path) -> None:
        p = make_session_path(tmp_path, "Moon")
        today = date.today().strftime("%Y-%m-%d")
        assert p.name.startswith(today)

    def test_does_not_create_directory(self, tmp_path: Path) -> None:
        p = make_session_path(tmp_path, "Vega", self._DATE)
        assert not p.exists()

    def test_raises_for_empty_target_after_sanitization(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="empty folder name"):
            make_session_path(tmp_path, "///", self._DATE)

    def test_image_root_as_string(self, tmp_path: Path) -> None:
        p = make_session_path(str(tmp_path), "Saturn", self._DATE)
        assert p.parent == tmp_path


# ── resolve_app_state_dir ─────────────────────────────────────────────────────

class TestResolveAppStateDir:
    def test_explicit_path_is_used(self, tmp_path: Path) -> None:
        explicit = tmp_path / "mystate"
        result = resolve_app_state_dir(explicit=explicit)
        assert result == explicit

    def test_explicit_path_is_created(self, tmp_path: Path) -> None:
        explicit = tmp_path / "newstate"
        assert not explicit.exists()
        resolve_app_state_dir(explicit=explicit)
        assert explicit.is_dir()

    def test_prefers_canonical_over_lowercase(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        canonical = tmp_path / ".SmartTScope"
        lowercase = tmp_path / ".smarttscope"
        canonical.mkdir()
        lowercase.mkdir(exist_ok=True)  # same dir on case-insensitive (Windows) filesystems
        monkeypatch.setattr("smart_telescope.domain.storage_config._CANONICAL", canonical)
        monkeypatch.setattr("smart_telescope.domain.storage_config._LOWERCASE", lowercase)
        assert resolve_app_state_dir() == canonical

    def test_falls_back_to_lowercase_when_canonical_absent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        canonical = tmp_path / ".SmartTScope"
        lowercase = tmp_path / ".smarttscope"
        lowercase.mkdir()
        monkeypatch.setattr("smart_telescope.domain.storage_config._CANONICAL", canonical)
        monkeypatch.setattr("smart_telescope.domain.storage_config._LOWERCASE", lowercase)
        assert resolve_app_state_dir() == lowercase

    def test_creates_canonical_when_neither_exists(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        canonical = tmp_path / ".SmartTScope"
        lowercase = tmp_path / ".smarttscope"
        monkeypatch.setattr("smart_telescope.domain.storage_config._CANONICAL", canonical)
        monkeypatch.setattr("smart_telescope.domain.storage_config._LOWERCASE", lowercase)
        result = resolve_app_state_dir()
        assert result == canonical
        assert canonical.is_dir()

    def test_explicit_string_path_works(self, tmp_path: Path) -> None:
        explicit = tmp_path / "strpath"
        result = resolve_app_state_dir(explicit=str(explicit))
        assert result == explicit
        assert explicit.is_dir()
