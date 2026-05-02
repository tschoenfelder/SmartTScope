"""Unit tests for domain/bahtinov.py — pure algorithm, no hardware."""

from __future__ import annotations

import math

import numpy as np
import pytest

from smart_telescope.domain.bahtinov import (
    BahtinovAnalyzer,
    CrossingAnalysisResult,
    SpikeLine,
    _classify_bahtinov,
    _gaussian_blur,
    _intersect,
)


# ── synthetic image helpers ───────────────────────────────────────────────────


def _blank(h: int = 256, w: int = 256) -> np.ndarray:
    return np.zeros((h, w), dtype=np.float32)


def _spike_image(
    size: int = 512,
    cx: int | None = None,
    cy: int | None = None,
    angles_deg: tuple[float, float, float] = (-20.0, 0.0, 20.0),
    spike_brightness: float = 0.8,
    core_brightness: float = 1.0,
    core_radius: int = 6,
) -> np.ndarray:
    """Synthetic Bahtinov image: bright star core + 3 spike lines."""
    img = np.zeros((size, size), dtype=np.float32)
    cx = cx if cx is not None else size // 2
    cy = cy if cy is not None else size // 2

    # Star core
    for dy in range(-core_radius, core_radius + 1):
        for dx in range(-core_radius, core_radius + 1):
            r = math.hypot(dx, dy)
            if r <= core_radius:
                yy, xx = cy + dy, cx + dx
                if 0 <= yy < size and 0 <= xx < size:
                    img[yy, xx] = core_brightness * max(0.0, 1.0 - r / core_radius)

    # Three spike lines through (cx, cy)
    for angle_deg in angles_deg:
        angle = math.radians(angle_deg)
        sin_a, cos_a = math.sin(angle), math.cos(angle)
        for t in range(-size // 2, size // 2 + 1):
            x = int(round(cx + t * sin_a))
            y = int(round(cy + t * cos_a))
            if 0 <= x < size and 0 <= y < size:
                img[y, x] = max(img[y, x], spike_brightness)

    return img


def _make_line(a: float, b: float, c: float, angle_deg: float = 0.0) -> SpikeLine:
    nrm = math.hypot(a, b)
    return SpikeLine(a=a / nrm, b=b / nrm, c=c / nrm, angle_deg=angle_deg, confidence=100.0)


# ── SpikeLine ─────────────────────────────────────────────────────────────────


class TestSpikeLine:
    def test_is_named_tuple(self) -> None:
        line = SpikeLine(a=1.0, b=0.0, c=-5.0, angle_deg=90.0, confidence=50.0)
        assert line.a == 1.0
        assert line.b == 0.0

    def test_fields_accessible_by_index(self) -> None:
        line = SpikeLine(a=0.0, b=1.0, c=-10.0, angle_deg=0.0, confidence=200.0)
        assert line[2] == -10.0  # c

    def test_immutable(self) -> None:
        line = SpikeLine(a=1.0, b=0.0, c=0.0, angle_deg=0.0, confidence=1.0)
        with pytest.raises((AttributeError, TypeError)):
            line.a = 2.0  # type: ignore[misc]


# ── CrossingAnalysisResult ────────────────────────────────────────────────────


class TestCrossingAnalysisResult:
    def _make_result(self) -> CrossingAnalysisResult:
        lines = [
            SpikeLine(a=0.0, b=1.0, c=-256.0, angle_deg=0.0, confidence=1000.0),
            SpikeLine(a=0.34, b=0.94, c=-300.0, angle_deg=20.0, confidence=900.0),
            SpikeLine(a=-0.34, b=0.94, c=-200.0, angle_deg=160.0, confidence=900.0),
        ]
        return CrossingAnalysisResult(
            object_center_px=(256.0, 256.0),
            lines=lines,
            common_crossing_point_px=(256.0, 256.0),
            pairwise_intersections_px=[(256.0, 256.0)] * 3,
            crossing_error_rms_px=1.5,
            crossing_error_max_px=2.0,
            focus_error_px=3.7,
            detection_confidence=0.92,
        )

    def test_to_dict_has_all_keys(self) -> None:
        d = self._make_result().to_dict()
        for key in (
            "object_center_px", "lines", "common_crossing_point_px",
            "pairwise_intersections_px", "crossing_error_rms_px",
            "crossing_error_max_px", "focus_error_px", "detection_confidence",
        ):
            assert key in d

    def test_to_dict_lines_count(self) -> None:
        assert len(self._make_result().to_dict()["lines"]) == 3

    def test_to_dict_focus_error_rounded(self) -> None:
        d = self._make_result().to_dict()
        assert d["focus_error_px"] == pytest.approx(3.7, abs=0.01)

    def test_to_dict_confidence_rounded(self) -> None:
        d = self._make_result().to_dict()
        assert d["detection_confidence"] == pytest.approx(0.92, abs=0.001)

    def test_to_dict_center_is_list(self) -> None:
        d = self._make_result().to_dict()
        assert isinstance(d["object_center_px"], list)
        assert len(d["object_center_px"]) == 2

    def test_frozen_dataclass(self) -> None:
        r = self._make_result()
        with pytest.raises((AttributeError, TypeError)):
            r.focus_error_px = 0.0  # type: ignore[misc]


# ── _gaussian_blur ────────────────────────────────────────────────────────────


class TestGaussianBlur:
    def test_output_shape_preserved(self) -> None:
        arr = np.ones((50, 80), dtype=np.float32)
        out = _gaussian_blur(arr, sigma=1.5)
        assert out.shape == (50, 80)

    def test_uniform_array_unchanged(self) -> None:
        arr = np.full((40, 40), 5.0, dtype=np.float32)
        out = _gaussian_blur(arr, sigma=2.0)
        np.testing.assert_allclose(out, 5.0, atol=1e-4)

    def test_output_dtype_is_float32(self) -> None:
        arr = np.random.default_rng(0).random((30, 30)).astype(np.float32)
        assert _gaussian_blur(arr, sigma=1.0).dtype == np.float32

    def test_smoothing_reduces_variance(self) -> None:
        rng = np.random.default_rng(7)
        arr = rng.random((64, 64)).astype(np.float32)
        blurred = _gaussian_blur(arr, sigma=3.0)
        assert blurred.var() < arr.var()

    def test_small_sigma(self) -> None:
        arr = np.eye(20, dtype=np.float32)
        out = _gaussian_blur(arr, sigma=0.5)
        assert out.shape == (20, 20)

    def test_non_negative_preserving(self) -> None:
        arr = np.abs(np.random.default_rng(1).standard_normal((32, 32))).astype(np.float32)
        out = _gaussian_blur(arr, sigma=1.5)
        assert float(out.min()) >= -1e-6


# ── _intersect ────────────────────────────────────────────────────────────────


class TestIntersect:
    def test_perpendicular_lines_at_origin(self) -> None:
        # x=0  →  a=1,b=0,c=0
        # y=0  →  a=0,b=1,c=0
        h = SpikeLine(a=1.0, b=0.0, c=0.0, angle_deg=90.0, confidence=1.0)
        v = SpikeLine(a=0.0, b=1.0, c=0.0, angle_deg=0.0,  confidence=1.0)
        x, y = _intersect(h, v)
        assert x == pytest.approx(0.0, abs=1e-9)
        assert y == pytest.approx(0.0, abs=1e-9)

    def test_known_intersection(self) -> None:
        # x=3  →  a=1,b=0,c=-3
        # y=7  →  a=0,b=1,c=-7
        l1 = SpikeLine(a=1.0, b=0.0, c=-3.0, angle_deg=90.0, confidence=1.0)
        l2 = SpikeLine(a=0.0, b=1.0, c=-7.0, angle_deg=0.0,  confidence=1.0)
        x, y = _intersect(l1, l2)
        assert x == pytest.approx(3.0, abs=1e-9)
        assert y == pytest.approx(7.0, abs=1e-9)

    def test_parallel_lines_return_origin(self) -> None:
        # Two horizontal lines — no intersection
        l1 = SpikeLine(a=0.0, b=1.0, c=-5.0,  angle_deg=0.0, confidence=1.0)
        l2 = SpikeLine(a=0.0, b=1.0, c=-10.0, angle_deg=0.0, confidence=1.0)
        x, y = _intersect(l1, l2)
        assert x == pytest.approx(0.0)
        assert y == pytest.approx(0.0)

    def test_diagonal_lines(self) -> None:
        # y = x   →  x - y = 0  →  a=1/√2, b=-1/√2, c=0
        # y = -x  →  x + y = 0  →  a=1/√2, b=1/√2,  c=0
        sq2 = math.sqrt(2.0)
        l1 = SpikeLine(a=1/sq2, b=-1/sq2, c=0.0, angle_deg=45.0,  confidence=1.0)
        l2 = SpikeLine(a=1/sq2, b=1/sq2,  c=0.0, angle_deg=135.0, confidence=1.0)
        x, y = _intersect(l1, l2)
        assert x == pytest.approx(0.0, abs=1e-9)
        assert y == pytest.approx(0.0, abs=1e-9)


# ── _classify_bahtinov ────────────────────────────────────────────────────────


class TestClassifyBahtinov:
    def _lines(self, angles: list[float]) -> list[SpikeLine]:
        return [SpikeLine(a=0.0, b=1.0, c=0.0, angle_deg=a, confidence=1.0) for a in angles]

    def test_middle_index_is_median_angle(self) -> None:
        lines = self._lines([160.0, 0.0, 20.0])  # angles sorted: 0, 20, 160
        mid, out1, out2 = _classify_bahtinov(lines)
        assert lines[mid].angle_deg == pytest.approx(20.0)

    def test_outer_indices_are_extremes(self) -> None:
        lines = self._lines([5.0, 85.0, 170.0])
        mid, out1, out2 = _classify_bahtinov(lines)
        outer_angles = sorted([lines[out1].angle_deg, lines[out2].angle_deg])
        assert outer_angles == pytest.approx([5.0, 170.0])

    def test_returns_three_distinct_indices(self) -> None:
        lines = self._lines([10.0, 90.0, 170.0])
        result = _classify_bahtinov(lines)
        assert len(set(result)) == 3

    def test_all_valid_indices(self) -> None:
        lines = self._lines([30.0, 90.0, 150.0])
        mid, out1, out2 = _classify_bahtinov(lines)
        for idx in (mid, out1, out2):
            assert 0 <= idx < 3

    def test_already_sorted_input(self) -> None:
        lines = self._lines([0.0, 20.0, 40.0])
        mid, _, _ = _classify_bahtinov(lines)
        assert lines[mid].angle_deg == pytest.approx(20.0)


# ── BahtinovAnalyzer.analyze() ────────────────────────────────────────────────


class TestBahtinovAnalyzerAnalyze:
    def test_returns_crossing_analysis_result(self) -> None:
        img = _spike_image()
        result = BahtinovAnalyzer().analyze(img)
        assert isinstance(result, CrossingAnalysisResult)

    def test_exactly_three_lines_detected(self) -> None:
        img = _spike_image()
        result = BahtinovAnalyzer().analyze(img)
        assert len(result.lines) == 3

    def test_raises_value_error_on_blank_image(self) -> None:
        with pytest.raises(ValueError, match="spike"):
            BahtinovAnalyzer().analyze(_blank())

    def test_focus_error_near_zero_for_centred_spikes(self) -> None:
        """Symmetric spikes ±20° either side of vertical → P_outer on middle spike → error ≈ 0."""
        img = _spike_image(angles_deg=(-20.0, 0.0, 20.0))
        result = BahtinovAnalyzer().analyze(img)
        assert abs(result.focus_error_px) < 15.0  # symmetric arrangement

    def test_object_center_near_image_centre(self) -> None:
        img = _spike_image(size=512)
        result = BahtinovAnalyzer().analyze(img)
        cx, cy = result.object_center_px
        assert abs(cx - 256) < 20
        assert abs(cy - 256) < 20

    def test_detection_confidence_in_range(self) -> None:
        img = _spike_image()
        result = BahtinovAnalyzer().analyze(img)
        assert 0.0 <= result.detection_confidence <= 1.0

    def test_crossing_error_rms_is_nonnegative(self) -> None:
        img = _spike_image()
        result = BahtinovAnalyzer().analyze(img)
        assert result.crossing_error_rms_px >= 0.0

    def test_pairwise_intersections_has_three_points(self) -> None:
        img = _spike_image()
        result = BahtinovAnalyzer().analyze(img)
        assert len(result.pairwise_intersections_px) == 3

    def test_common_crossing_is_mean_of_pairwise(self) -> None:
        img = _spike_image()
        result = BahtinovAnalyzer().analyze(img)
        pts = result.pairwise_intersections_px
        expected_cx = sum(p[0] for p in pts) / 3
        expected_cy = sum(p[1] for p in pts) / 3
        cx, cy = result.common_crossing_point_px
        assert cx == pytest.approx(expected_cx, abs=1e-6)
        assert cy == pytest.approx(expected_cy, abs=1e-6)

    def test_star_off_centre(self) -> None:
        """Star at (150, 180) — finder should still locate it."""
        img = _spike_image(size=512, cx=150, cy=180)
        result = BahtinovAnalyzer().analyze(img)
        cx, cy = result.object_center_px
        assert abs(cx - 150) < 25
        assert abs(cy - 180) < 25

    def test_each_line_has_unit_normal(self) -> None:
        img = _spike_image()
        result = BahtinovAnalyzer().analyze(img)
        for line in result.lines:
            nrm = math.hypot(line.a, line.b)
            assert nrm == pytest.approx(1.0, abs=1e-5)

    def test_to_dict_roundtrip(self) -> None:
        img = _spike_image()
        result = BahtinovAnalyzer().analyze(img)
        d = result.to_dict()
        assert d["focus_error_px"] == pytest.approx(result.focus_error_px, abs=0.01)
        assert d["detection_confidence"] == pytest.approx(result.detection_confidence, abs=0.001)


# ── BahtinovAnalyzer — constructor params ─────────────────────────────────────


class TestBahtinovAnalyzerParams:
    def test_custom_roi_size(self) -> None:
        img = _spike_image(size=512)
        result = BahtinovAnalyzer(roi_size=200).analyze(img)
        assert isinstance(result, CrossingAnalysisResult)

    def test_custom_core_radius(self) -> None:
        img = _spike_image(size=512)
        result = BahtinovAnalyzer(core_radius=5).analyze(img)
        assert len(result.lines) == 3

    def test_custom_n_angles(self) -> None:
        img = _spike_image(size=512)
        result = BahtinovAnalyzer(n_angles=90).analyze(img)
        assert len(result.lines) == 3

    def test_blank_image_raises_regardless_of_params(self) -> None:
        with pytest.raises(ValueError):
            BahtinovAnalyzer(threshold_percentile=50.0).analyze(_blank())


# ── _find_brightest_object ────────────────────────────────────────────────────


class TestFindBrightestObject:
    def _analyzer(self) -> BahtinovAnalyzer:
        return BahtinovAnalyzer()

    def test_locates_bright_spot(self) -> None:
        img = _blank(128, 128)
        img[60:66, 60:66] = 1.0
        cx, cy = self._analyzer()._find_brightest_object(img.astype(np.float64))
        assert abs(cx - 62.5) < 5
        assert abs(cy - 62.5) < 5

    def test_uniform_image_does_not_raise(self) -> None:
        img = np.ones((64, 64), dtype=np.float64)
        cx, cy = self._analyzer()._find_brightest_object(img)
        assert 0 <= cx < 64
        assert 0 <= cy < 64

    def test_zero_image_returns_peak(self) -> None:
        img = np.zeros((64, 64), dtype=np.float64)
        cx, cy = self._analyzer()._find_brightest_object(img)
        assert 0 <= cx < 64
        assert 0 <= cy < 64
