"""Tests for the LiveAnalysis adapter shim — M10-004."""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from smart_telescope.services import live_analysis_shim as shim


class _FakeCamera:
    def get_exposure_ms(self) -> float: return 500.0
    def get_gain(self) -> int: return 101
    def get_black_level(self) -> int: return 32
    def get_bit_depth(self) -> int: return 16
    def get_conversion_gain(self): return SimpleNamespace(name="HCG")


def _frame(pixels=None, exposure_s=1.5, header=None):
    return SimpleNamespace(
        pixels=pixels if pixels is not None else np.zeros((16, 16), dtype=np.float32),
        exposure_seconds=exposure_s,
        header=header if header is not None else {},
    )


class TestBuildCameraInfo:
    def test_frame_facts_win_over_camera_queries(self):
        # EXPTIME produced the pixels; BITDEPTH reflects the detected shift.
        info = shim.build_camera_info(
            _FakeCamera(), frame=_frame(exposure_s=1.5, header={"BITDEPTH": 12}),
        )
        assert info["exposure_s"] == 1.5
        assert info["bit_depth"] == 12
        assert info["gain"] == 101
        assert info["offset"] == 32
        assert info["conversion_gain"] == "HCG"
        assert info["raw_mode"] is True
        assert info["binning"] == 1

    def test_without_frame_falls_back_to_camera_state(self):
        info = shim.build_camera_info(_FakeCamera())
        assert info["exposure_s"] == 0.5
        assert info["bit_depth"] == 16

    def test_camera_query_failures_omit_keys(self):
        class Broken:
            def __getattr__(self, name):
                def boom(*a, **k):
                    raise RuntimeError("no camera")
                return boom
        info = shim.build_camera_info(Broken())
        assert info == {"binning": 1, "raw_mode": True}


class TestAnalyze:
    def test_calls_pinned_module_with_native_pixels(self):
        # Real call against the pinned smarttscope_live_analysis package —
        # verifies the v0.1.0 API contract this shim encodes.
        info = shim.build_camera_info(_FakeCamera(), frame=_frame())
        result = shim.analyze(info, _frame(), previous_star_state=None)
        assert result["single_frame"]["stars_found"] == 0
        assert "recommendation" in result
        assert "state" in result
        # Rolling state round-trips into the next call.
        again = shim.analyze(info, _frame(), previous_star_state=result["state"])
        assert again["frame_index"] == result["frame_index"] + 1

    def test_available_reports_true_here(self):
        assert shim.live_analysis_available() is True
