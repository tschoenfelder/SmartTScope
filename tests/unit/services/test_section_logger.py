"""Unit tests for SectionLogger (M8-014 / REQ-LOG-001)."""
from __future__ import annotations

import logging
from pathlib import Path

import pytest

from smart_telescope.services.section_logger import LOG_SECTIONS, SectionLogger


# ── helpers ────────────────────────────────────────────────────────────────────

SESSION = "abcd1234-0000-0000-0000-000000000000"
SLUG    = SESSION[:8]  # "abcd1234"


def _svc(log_dir: str | None = None) -> SectionLogger:
    return SectionLogger(session_id=SESSION, log_dir=log_dir)


# ── TestSectionList ────────────────────────────────────────────────────────────

class TestSectionList:
    def test_exactly_12_sections(self):
        assert len(LOG_SECTIONS) == 12

    def test_required_section_names_present(self):
        required = {
            "startup", "stage1_time_location", "mount", "camera", "auto_gain",
            "autofocus", "collimation", "plate_solve", "goto", "click_to_center",
            "extended_setup_check", "github_delivery",
        }
        assert required == set(LOG_SECTIONS)


# ── TestNoLogDir ──────────────────────────────────────────────────────────────

class TestNoLogDir:
    def test_get_paths_returns_12_keys(self):
        svc = _svc()
        assert set(svc.get_paths().keys()) == set(LOG_SECTIONS)

    def test_all_paths_none_when_no_log_dir(self):
        svc = _svc()
        assert all(v is None for v in svc.get_paths().values())

    def test_get_returns_adapter_for_every_section(self):
        svc = _svc()
        for section in LOG_SECTIONS:
            adapter = svc.get(section)
            assert adapter is not None

    def test_adapter_extra_contains_session_id(self):
        svc = _svc()
        adapter = svc.get("goto")
        assert adapter.extra["session_id"] == SLUG

    def test_adapter_extra_contains_section_name(self):
        svc = _svc()
        adapter = svc.get("mount")
        assert adapter.extra["section"] == "mount"

    def test_loggers_propagate_to_parent(self):
        _svc()
        for section in LOG_SECTIONS:
            logger = logging.getLogger(f"smart_telescope.section.{section}")
            assert logger.propagate is True

    def test_get_unknown_section_returns_fallback_adapter(self):
        svc = _svc()
        adapter = svc.get("nonexistent_section")
        assert adapter is not None
        assert adapter.extra["section"] == "nonexistent_section"


# ── TestWithLogDir ─────────────────────────────────────────────────────────────

class TestWithLogDir:
    def test_paths_set_for_all_sections(self, tmp_path: Path):
        svc = _svc(log_dir=str(tmp_path))
        paths = svc.get_paths()
        assert all(v is not None for v in paths.values())

    def test_path_structure_is_correct(self, tmp_path: Path):
        svc = _svc(log_dir=str(tmp_path))
        paths = svc.get_paths()
        for section, path in paths.items():
            assert path is not None
            p = Path(path)
            assert p.parent.name == SLUG
            assert p.name == f"{section}.log"

    def test_log_files_created_on_disk(self, tmp_path: Path):
        svc = _svc(log_dir=str(tmp_path))
        paths = svc.get_paths()
        for section, path in paths.items():
            assert path is not None
            assert Path(path).exists(), f"Missing log file for section {section!r}"

    def test_get_paths_returns_copy(self, tmp_path: Path):
        svc = _svc(log_dir=str(tmp_path))
        p1 = svc.get_paths()
        p2 = svc.get_paths()
        assert p1 == p2
        assert p1 is not p2  # independent copy

    def test_close_removes_file_handlers(self, tmp_path: Path):
        svc = _svc(log_dir=str(tmp_path))
        svc.close()
        for section in LOG_SECTIONS:
            logger = logging.getLogger(f"smart_telescope.section.{section}")
            file_handlers = [h for h in logger.handlers if isinstance(h, logging.FileHandler)]
            assert file_handlers == [], f"File handler still attached for section {section!r}"
