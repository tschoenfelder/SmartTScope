"""Tests for click_refinement domain — M8-026 / REQ-CLICK-002."""
from __future__ import annotations

import numpy as np
import pytest

from smart_telescope.domain.click_refinement import (
    RefinedClick,
    refine_click,
)


# ── helpers ─────────────────────────────────────────────────────────────────

def _dark_frame(h: int = 200, w: int = 200, bg: float = 100.0) -> np.ndarray:
    """Uniform background frame."""
    return np.full((h, w), bg, dtype=np.float32)


def _star_frame(
    h: int = 200, w: int = 200, bg: float = 100.0,
    star_x: int = 80, star_y: int = 90, peak: float = 5000.0, radius: int = 5,
) -> np.ndarray:
    """Gaussian-like star blob on a flat background."""
    frame = _dark_frame(h, w, bg)
    for dy in range(-radius * 2, radius * 2 + 1):
        for dx in range(-radius * 2, radius * 2 + 1):
            iy, ix = star_y + dy, star_x + dx
            if 0 <= iy < h and 0 <= ix < w:
                r2 = (dx ** 2 + dy ** 2) / (radius ** 2)
                frame[iy, ix] += float(peak * np.exp(-r2))
    return frame


def _donut_frame(
    h: int = 200, w: int = 200, bg: float = 500.0,
    cx: int = 100, cy: int = 100, inner_r: int = 10, outer_r: int = 25,
) -> np.ndarray:
    """Ring of bright pixels with a dark shadow in the centre."""
    frame = _dark_frame(h, w, bg * 0.3)  # frame darker than ring
    ys, xs = np.ogrid[:h, :w]
    dist = np.sqrt((xs - cx) ** 2 + (ys - cy) ** 2)
    ring = (dist >= inner_r) & (dist <= outer_r)
    frame[ring] = bg
    return frame.astype(np.float32)


# ── RefinedClick dataclass ──────────────────────────────────────────────────

def test_refined_click_to_dict():
    rc = RefinedClick(10, 20, 12, 22, "star_centroid", 0.8, False)
    d = rc.to_dict()
    assert d["raw_x"] == 10
    assert d["refined_x"] == 12
    assert d["method"] == "star_centroid"
    assert d["fallback"] is False


def test_refined_click_to_json_line():
    rc = RefinedClick(1, 2, 3, 4, "raw_fallback", 0.0, True)
    line = rc.to_json_line()
    import json
    data = json.loads(line)
    assert data["event"] == "CLICK_REFINED"
    assert data["method"] == "raw_fallback"


# ── star_centroid mode ──────────────────────────────────────────────────────

def test_star_centroid_finds_star():
    frame = _star_frame(star_x=80, star_y=90)
    result = refine_click(frame, click_x=85, click_y=85, mode="star_centroid")
    assert not result.fallback
    assert abs(result.refined_x - 80) <= 3
    assert abs(result.refined_y - 90) <= 3


def test_star_centroid_confidence_positive():
    frame = _star_frame(star_x=80, star_y=90)
    result = refine_click(frame, click_x=82, click_y=88, mode="star_centroid")
    assert result.confidence > 0.0


def test_star_centroid_fallback_on_uniform():
    frame = _dark_frame()
    result = refine_click(frame, click_x=100, click_y=100, mode="star_centroid")
    assert result.fallback
    assert result.method == "raw_fallback"
    assert result.confidence == 0.0


def test_star_centroid_fallback_returns_raw_coords():
    frame = _dark_frame()
    result = refine_click(frame, click_x=55, click_y=66, mode="star_centroid")
    assert result.refined_x == 55
    assert result.refined_y == 66


def test_star_centroid_search_radius_limits():
    """Star outside search_radius=10 should not be found."""
    frame = _star_frame(star_x=80, star_y=90)
    result = refine_click(frame, click_x=10, click_y=10, mode="star_centroid", search_radius=10)
    assert result.fallback


def test_star_centroid_method_label():
    frame = _star_frame(star_x=80, star_y=90)
    result = refine_click(frame, click_x=82, click_y=88, mode="star_centroid")
    if not result.fallback:
        assert result.method == "star_centroid"


# ── ring_center mode ────────────────────────────────────────────────────────

def test_ring_center_finds_donut_shadow():
    frame = _donut_frame(cx=100, cy=100)
    result = refine_click(frame, click_x=105, click_y=100, mode="ring_center")
    assert not result.fallback
    assert abs(result.refined_x - 100) <= 5
    assert abs(result.refined_y - 100) <= 5


def test_ring_center_confidence_positive():
    frame = _donut_frame(cx=100, cy=100)
    result = refine_click(frame, click_x=100, click_y=100, mode="ring_center")
    assert result.confidence > 0.0


def test_ring_center_fallback_on_uniform():
    frame = _dark_frame()
    result = refine_click(frame, click_x=100, click_y=100, mode="ring_center")
    assert result.fallback


def test_ring_center_method_label():
    frame = _donut_frame(cx=100, cy=100)
    result = refine_click(frame, click_x=100, click_y=100, mode="ring_center")
    if not result.fallback:
        assert result.method == "ring_center"


# ── unknown mode fallback ───────────────────────────────────────────────────

def test_unknown_mode_returns_raw_fallback():
    frame = _star_frame(star_x=80, star_y=90)
    result = refine_click(frame, click_x=80, click_y=90, mode="unknown_mode")
    assert result.fallback
    assert result.method == "raw_fallback"


# ── edge cases ──────────────────────────────────────────────────────────────

def test_click_near_border_does_not_crash():
    frame = _star_frame(star_x=5, star_y=5)
    result = refine_click(frame, click_x=0, click_y=0, mode="star_centroid")
    # Should not raise; may or may not find star
    assert isinstance(result, RefinedClick)


def test_click_outside_frame_returns_fallback():
    frame = _dark_frame(h=100, w=100)
    result = refine_click(frame, click_x=500, click_y=500, mode="star_centroid")
    assert result.fallback
