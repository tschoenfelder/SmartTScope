"""Unit tests for services/frame_analyzer.py."""
from __future__ import annotations

import logging
import types
from unittest.mock import MagicMock

import numpy as np
import pytest

from smart_telescope.domain.star_count import StarCountResult
from smart_telescope.services.frame_analyzer import (
    ExternalFrameAnalyzer,
    FrameAnalyzerProtocol,
    load_external_analyzer,
)


def _make_result(**kwargs) -> StarCountResult:
    defaults = dict(
        stars_found=5,
        image_quality="usable",
        suggested_exposure_s=None,
        suggested_gain=None,
        suggested_offset=None,
        focus_warning=False,
        notes=(),
        sources=(),
    )
    defaults.update(kwargs)
    return StarCountResult(**defaults)


class TestLoadExternalAnalyzer:
    def test_empty_string_returns_none(self) -> None:
        assert load_external_analyzer("") is None

    def test_nonexistent_module_returns_none(self) -> None:
        assert load_external_analyzer("_no_such_module_xyz_12345") is None

    def test_nonexistent_module_logs_warning(self, caplog) -> None:
        with caplog.at_level(logging.WARNING):
            load_external_analyzer("_no_such_module_xyz_12345")
        assert any("not available" in r.message for r in caplog.records)

    def test_module_without_analyze_frame_returns_none(self, monkeypatch) -> None:
        fake_mod = types.ModuleType("fake_mod")
        monkeypatch.setattr(
            "smart_telescope.services.frame_analyzer.importlib.import_module",
            lambda name: fake_mod,
        )
        assert load_external_analyzer("fake_mod") is None

    def test_module_without_analyze_frame_logs_warning(self, monkeypatch, caplog) -> None:
        fake_mod = types.ModuleType("fake_mod")
        monkeypatch.setattr(
            "smart_telescope.services.frame_analyzer.importlib.import_module",
            lambda name: fake_mod,
        )
        with caplog.at_level(logging.WARNING):
            load_external_analyzer("fake_mod")
        assert any("no callable analyze_frame" in r.message for r in caplog.records)

    def test_valid_module_returns_analyzer(self, monkeypatch) -> None:
        expected = _make_result(stars_found=7)
        fake_mod = types.ModuleType("good_mod")
        fake_mod.analyze_frame = lambda img, *, exposure_s, gain, offset: expected  # type: ignore[attr-defined]
        monkeypatch.setattr(
            "smart_telescope.services.frame_analyzer.importlib.import_module",
            lambda name: fake_mod,
        )
        analyzer = load_external_analyzer("good_mod")
        assert analyzer is not None
        assert isinstance(analyzer, FrameAnalyzerProtocol)


class TestExternalFrameAnalyzer:
    def _make_analyzer(self, fn=None):
        if fn is None:
            fn = lambda img, *, exposure_s, gain, offset: _make_result()
        return ExternalFrameAnalyzer(fn, "test_module")

    def test_passes_image_through(self) -> None:
        captured = {}

        def fn(img, *, exposure_s, gain, offset):
            captured["img"] = img
            return _make_result()

        analyzer = ExternalFrameAnalyzer(fn, "m")
        img = np.zeros((4, 4), dtype=np.float32)
        analyzer.analyze_frame(img, exposure_s=1.0, gain=200, offset=10)
        assert captured["img"] is img

    def test_passes_kwargs_correctly(self) -> None:
        captured = {}

        def fn(img, *, exposure_s, gain, offset):
            captured.update(exposure_s=exposure_s, gain=gain, offset=offset)
            return _make_result()

        analyzer = ExternalFrameAnalyzer(fn, "m")
        analyzer.analyze_frame(np.zeros((4, 4)), exposure_s=2.5, gain=300, offset=50)
        assert captured == {"exposure_s": 2.5, "gain": 300, "offset": 50}

    def test_returns_star_count_result(self) -> None:
        expected = _make_result(stars_found=42)
        analyzer = self._make_analyzer(lambda img, *, exposure_s, gain, offset: expected)
        result = analyzer.analyze_frame(np.zeros((4, 4)), exposure_s=None, gain=None, offset=None)
        assert result is expected

    def test_none_kwargs_passed_through(self) -> None:
        captured = {}

        def fn(img, *, exposure_s, gain, offset):
            captured.update(exposure_s=exposure_s, gain=gain, offset=offset)
            return _make_result()

        analyzer = ExternalFrameAnalyzer(fn, "m")
        analyzer.analyze_frame(np.zeros((4, 4)), exposure_s=None, gain=None, offset=None)
        assert captured == {"exposure_s": None, "gain": None, "offset": None}

    def test_repr_includes_module_name(self) -> None:
        analyzer = self._make_analyzer()
        assert "test_module" in repr(analyzer)

    def test_satisfies_protocol(self) -> None:
        analyzer = self._make_analyzer()
        assert isinstance(analyzer, FrameAnalyzerProtocol)
