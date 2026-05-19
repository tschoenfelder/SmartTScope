"""Unit tests for find_catalog() — no ASTAP binary required."""
from pathlib import Path

import pytest

from smart_telescope.adapters.astap.solver import find_catalog


def _plant(directory: Path, filename: str = "h000.290") -> Path:
    f = directory / filename
    f.write_bytes(b"fake-catalog")
    return f


class TestFindCatalog:
    def test_returns_none_when_no_catalog_anywhere(self, tmp_path: Path) -> None:
        assert find_catalog(astap_exe=str(tmp_path / "astap")) is None

    def test_finds_catalog_in_same_dir_as_astap(self, tmp_path: Path) -> None:
        _plant(tmp_path)
        result = find_catalog(astap_exe=str(tmp_path / "astap"))
        assert result == tmp_path

    def test_returns_none_when_dir_has_no_290_files(self, tmp_path: Path) -> None:
        (tmp_path / "readme.txt").write_text("hello")
        assert find_catalog(astap_exe=str(tmp_path / "astap")) is None

    def test_finds_any_290_extension(self, tmp_path: Path) -> None:
        _plant(tmp_path, "h042.290")
        result = find_catalog(astap_exe=str(tmp_path / "astap"))
        assert result == tmp_path

    def test_astap_dir_searched_before_system_dirs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        astap_dir = tmp_path / "astap_exe"
        astap_dir.mkdir()
        sys_dir = tmp_path / "sys"
        sys_dir.mkdir()
        _plant(astap_dir)
        _plant(sys_dir, "h001.290")

        monkeypatch.setattr(
            "smart_telescope.adapters.astap.solver._CATALOG_SEARCH_DIRS",
            [sys_dir],
        )
        result = find_catalog(astap_exe=str(astap_dir / "astap"))
        assert result == astap_dir

    def test_falls_back_to_system_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sys_dir = tmp_path / "sys"
        sys_dir.mkdir()
        _plant(sys_dir)

        monkeypatch.setattr(
            "smart_telescope.adapters.astap.solver._CATALOG_SEARCH_DIRS",
            [sys_dir],
        )
        result = find_catalog(astap_exe=None)
        assert result == sys_dir

    def test_returns_none_without_astap_exe_and_empty_sys_dirs(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "smart_telescope.adapters.astap.solver._CATALOG_SEARCH_DIRS", []
        )
        assert find_catalog(astap_exe=None) is None

    # D-series (.1476) support ─────────────────────────────────────────────────

    def test_finds_d80_catalog_by_1476_extension(self, tmp_path: Path) -> None:
        _plant(tmp_path, "d80_3402.1476")
        result = find_catalog(astap_exe=str(tmp_path / "astap"))
        assert result == tmp_path

    def test_finds_d80_catalog_in_subdirectory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sub = tmp_path / "d80"
        sub.mkdir()
        _plant(sub, "d80_0001.1476")

        monkeypatch.setattr(
            "smart_telescope.adapters.astap.solver._CATALOG_SEARCH_DIRS",
            [tmp_path],
        )
        result = find_catalog(astap_exe=None)
        assert result == sub

    def test_does_not_return_dir_with_only_unrelated_files(self, tmp_path: Path) -> None:
        (tmp_path / "d80_3402.fits").write_bytes(b"fake")
        assert find_catalog(astap_exe=str(tmp_path / "astap")) is None
