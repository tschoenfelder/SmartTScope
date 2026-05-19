"""Unit tests for domain/planet_detection.py (AGT-8-1)."""
from __future__ import annotations

import numpy as np
import pytest

from smart_telescope.domain.planet_detection import DetectedObject, detect_planet

BIT_DEPTH = 16
ADC_MAX   = float((1 << BIT_DEPTH) - 1)

H, W = 64, 64


# ── Frame helpers ─────────────────────────────────────────────────────────────

def _disk_frame(peak_frac: float, radius: int = 8, bg_frac: float = 0.001) -> np.ndarray:
    """Frame with a circular bright disk centred at (H//2, W//2)."""
    cy, cx = H // 2, W // 2
    y, x = np.ogrid[:H, :W]
    disk = (y - cy) ** 2 + (x - cx) ** 2 <= radius ** 2
    pix = np.full((H, W), bg_frac * ADC_MAX, dtype=np.float32)
    pix[disk] = float(peak_frac * ADC_MAX)
    return pix


def _hot_pixel_frame(peak_frac: float = 1.0, bg_frac: float = 0.001) -> np.ndarray:
    """Frame with a single hot pixel and otherwise dim background."""
    pix = np.full((H, W), bg_frac * ADC_MAX, dtype=np.float32)
    pix[H // 2, W // 2] = float(peak_frac * ADC_MAX)
    return pix


def _dark_frame() -> np.ndarray:
    return np.zeros((H, W), dtype=np.float32)


def _stars_and_disk_frame(disk_peak: float, star_peak: float, n_stars: int = 5) -> np.ndarray:
    """Frame with one disk plus several isolated star-like blobs (area ≈ 4)."""
    pix = _disk_frame(disk_peak, radius=8)
    rng = np.random.default_rng(42)
    for _ in range(n_stars):
        r = int(rng.integers(2, H - 2))
        c = int(rng.integers(2, W - 2))
        # 2×2 bright patch (area = 4) so they qualify as components
        pix[r : r + 2, c : c + 2] = float(star_peak * ADC_MAX)
    return pix


# ── Basic detection ───────────────────────────────────────────────────────────

class TestDetectPlanet:
    def test_disk_returns_detected_object(self) -> None:
        pix = _disk_frame(0.60)
        result = detect_planet(pix, BIT_DEPTH)
        assert result is not None
        assert isinstance(result, DetectedObject)

    def test_dark_frame_returns_none(self) -> None:
        result = detect_planet(_dark_frame(), BIT_DEPTH)
        assert result is None

    def test_single_hot_pixel_returns_none(self) -> None:
        # Area = 1 < _MIN_AREA_PX → rejected
        result = detect_planet(_hot_pixel_frame(1.0), BIT_DEPTH)
        assert result is None

    def test_center_near_frame_center(self) -> None:
        pix = _disk_frame(0.60, radius=8)
        result = detect_planet(pix, BIT_DEPTH)
        assert result is not None
        r, c = result.center_px
        assert abs(r - H // 2) <= 2
        assert abs(c - W // 2) <= 2

    def test_radius_approximates_input(self) -> None:
        import math
        radius_in = 8
        pix = _disk_frame(0.60, radius=radius_in)
        result = detect_planet(pix, BIT_DEPTH)
        assert result is not None
        # radius_px = √(area/π); area of disk ≈ π r² so radius_px ≈ r
        assert abs(result.radius_px - radius_in) <= 2.0

    def test_peak_frac_matches_frame_peak(self) -> None:
        pix = _disk_frame(0.70, radius=8)
        result = detect_planet(pix, BIT_DEPTH)
        assert result is not None
        assert result.peak_frac == pytest.approx(0.70, abs=0.01)

    def test_unsaturated_disk_saturation_pct_zero(self) -> None:
        pix = _disk_frame(0.60, radius=8)
        result = detect_planet(pix, BIT_DEPTH)
        assert result is not None
        assert result.saturation_pct == pytest.approx(0.0, abs=0.1)

    def test_fully_saturated_disk_saturation_pct_100(self) -> None:
        pix = _disk_frame(1.0, radius=8)
        result = detect_planet(pix, BIT_DEPTH)
        assert result is not None
        assert result.saturation_pct == pytest.approx(100.0, abs=0.1)

    def test_small_component_below_min_area_rejected(self) -> None:
        # 3-pixel L-shape: area = 3 < _MIN_AREA_PX = 4 → should be rejected
        pix = np.full((H, W), 0.001 * ADC_MAX, dtype=np.float32)
        pix[32, 32] = float(0.9 * ADC_MAX)
        pix[32, 33] = float(0.9 * ADC_MAX)
        pix[33, 32] = float(0.9 * ADC_MAX)
        result = detect_planet(pix, BIT_DEPTH)
        # 3 pixels < MIN_AREA_PX=4 → no qualifying component
        assert result is None


# ── Scoring: disk beats stars ─────────────────────────────────────────────────

class TestScoring:
    def test_disk_wins_over_bright_stars(self) -> None:
        # Disk at 0.50, several small star blobs at 0.85
        pix = _stars_and_disk_frame(disk_peak=0.50, star_peak=0.85, n_stars=6)
        result = detect_planet(pix, BIT_DEPTH)
        assert result is not None
        # The winning component should be centred near the disk centre
        r, c = result.center_px
        assert abs(r - H // 2) <= 3
        assert abs(c - W // 2) <= 3

    def test_larger_disk_wins_over_smaller_disk(self) -> None:
        # Two disks in same frame — larger should win
        pix = np.full((H, W), 0.001 * ADC_MAX, dtype=np.float32)
        y, x = np.ogrid[:H, :W]
        big_disk   = (y - 32) ** 2 + (x - 16) ** 2 <= 10 ** 2
        small_disk = (y - 32) ** 2 + (x - 48) ** 2 <= 4 ** 2
        pix[big_disk]   = float(0.70 * ADC_MAX)
        pix[small_disk] = float(0.80 * ADC_MAX)   # smaller but brighter
        result = detect_planet(pix, BIT_DEPTH)
        assert result is not None
        # Big disk centre is at col 16
        _, c = result.center_px
        assert abs(c - 16) <= 3


# ── Edge cases ────────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_frame_max_below_threshold_returns_none(self) -> None:
        # All pixels at 0.005 → pix_max < 0.01 → dark
        pix = np.full((H, W), 0.005 * ADC_MAX, dtype=np.float32)
        assert detect_planet(pix, BIT_DEPTH) is None

    def test_different_bit_depths(self) -> None:
        for bd in (8, 12, 14, 16):
            adc = float((1 << bd) - 1)
            pix = np.full((H, W), 0.001 * adc, dtype=np.float32)
            cy, cx = H // 2, W // 2
            y, x = np.ogrid[:H, :W]
            pix[(y - cy) ** 2 + (x - cx) ** 2 <= 8 ** 2] = float(0.6 * adc)
            result = detect_planet(pix, bd)
            assert result is not None, f"bit_depth={bd}"
            assert result.peak_frac == pytest.approx(0.6, abs=0.01)
