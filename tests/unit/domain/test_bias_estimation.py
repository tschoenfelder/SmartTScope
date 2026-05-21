import numpy as np
import pytest
from smart_telescope.domain.bias_estimation import (
    BiasFrameStats,
    OffsetSweepPoint,
    BiasEstimationResult,
    analyze_frame,
    ZERO_CLIP_THRESHOLD,
    DEFAULT_SWEEP_OFFSETS,
)


# --- analyze_frame ---

def test_analyze_frame_all_zero_pixels():
    pixels = np.zeros((100, 100), dtype=np.float32)
    stats = analyze_frame(pixels, frame_index=0)
    assert stats.min_val == 0
    assert stats.max_val == 0
    assert stats.mean == pytest.approx(0.0)
    assert stats.zero_count == 10000
    assert stats.zero_fraction == pytest.approx(1.0)


def test_analyze_frame_no_zero_pixels():
    pixels = np.full((100, 100), 50, dtype=np.float32)
    stats = analyze_frame(pixels, frame_index=0)
    assert stats.min_val == 50
    assert stats.zero_count == 0
    assert stats.zero_fraction == pytest.approx(0.0)


def test_analyze_frame_partial_zeros():
    pixels = np.full((100, 100), 10, dtype=np.float32)
    pixels[:10, :] = 0  # 1000 zero pixels out of 10000
    stats = analyze_frame(pixels, frame_index=0)
    assert stats.zero_count == 1000
    assert stats.zero_fraction == pytest.approx(0.1)


def test_analyze_frame_mean_median_std():
    rng = np.random.default_rng(42)
    pixels = rng.normal(loc=150.0, scale=10.0, size=(200, 200)).astype(np.float32)
    pixels = np.clip(pixels, 0, 65535)
    stats = analyze_frame(pixels, frame_index=2)
    assert stats.frame_index == 2
    assert abs(stats.mean - 150.0) < 2.0
    assert abs(stats.median - 150.0) < 2.0
    assert abs(stats.std - 10.0) < 2.0


def test_analyze_frame_histogram_has_256_bins():
    pixels = np.arange(256, dtype=np.float32).reshape(16, 16)
    stats = analyze_frame(pixels, frame_index=0)
    assert len(stats.histogram) == 256


# --- OffsetSweepPoint is_safe ---

def test_sweep_point_safe_when_below_threshold():
    pt = OffsetSweepPoint(offset=50, zero_fraction=0.0001, min_val=5)
    assert pt.is_safe is True


def test_sweep_point_unsafe_when_above_threshold():
    pt = OffsetSweepPoint(offset=0, zero_fraction=0.005, min_val=0)
    assert pt.is_safe is False


def test_sweep_point_threshold_boundary():
    # ZERO_CLIP_THRESHOLD = 0.001 (0.1%)
    pt_just_safe   = OffsetSweepPoint(offset=0, zero_fraction=ZERO_CLIP_THRESHOLD - 1e-9, min_val=1)
    pt_just_unsafe = OffsetSweepPoint(offset=0, zero_fraction=ZERO_CLIP_THRESHOLD, min_val=0)
    assert pt_just_safe.is_safe is True
    assert pt_just_unsafe.is_safe is False


# --- BiasEstimationResult.recommended_offset logic ---

def test_result_recommends_lowest_safe_offset():
    sweep = [
        OffsetSweepPoint(offset=0,  zero_fraction=0.05,   min_val=0),   # unsafe
        OffsetSweepPoint(offset=5,  zero_fraction=0.002,  min_val=0),   # unsafe
        OffsetSweepPoint(offset=10, zero_fraction=0.0005, min_val=2),   # safe <- first safe
        OffsetSweepPoint(offset=20, zero_fraction=0.0,    min_val=15),  # safe
    ]
    result = BiasEstimationResult(
        camera_model="G3M678M", gain_mode_name="LCG",
        frame_count=10, mean_stats=None,
        sweep=sweep,
    )
    assert result.recommended_offset == 10


def test_result_recommends_zero_when_no_clipping():
    sweep = [
        OffsetSweepPoint(offset=0, zero_fraction=0.0, min_val=5),
    ]
    result = BiasEstimationResult(
        camera_model="G3M678M", gain_mode_name="LCG",
        frame_count=10, mean_stats=None,
        sweep=sweep,
    )
    assert result.recommended_offset == 0


def test_result_recommends_max_when_all_unsafe():
    sweep = [
        OffsetSweepPoint(offset=i*10, zero_fraction=0.01, min_val=0)
        for i in range(5)
    ]
    result = BiasEstimationResult(
        camera_model="G3M678M", gain_mode_name="LCG",
        frame_count=10, mean_stats=None,
        sweep=sweep,
    )
    # Falls back to highest tested offset when nothing is safe
    assert result.recommended_offset == 40
    assert result.safe is False


def test_result_toml_snippet():
    sweep = [OffsetSweepPoint(offset=150, zero_fraction=0.0, min_val=10)]
    result = BiasEstimationResult(
        camera_model="G3M678M", gain_mode_name="LCG",
        frame_count=10, mean_stats=None,
        sweep=sweep,
    )
    snippet = result.toml_snippet()
    assert "[camera_offsets.G3M678M]" in snippet
    assert "lcg = 150" in snippet


def test_default_sweep_offsets_has_expected_values():
    assert DEFAULT_SWEEP_OFFSETS == [0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200]


import pytest as _pytest

@_pytest.mark.parametrize("gain_name,expected_key", [
    ("LCG", "lcg"),
    ("HCG", "hcg"),
    ("HDR", "hdr"),
])
def test_result_toml_snippet_gain_mode_key(gain_name, expected_key):
    sweep = [OffsetSweepPoint(offset=100, zero_fraction=0.0, min_val=10)]
    result = BiasEstimationResult(
        camera_model="TestCam", gain_mode_name=gain_name,
        frame_count=5, mean_stats=None,
        sweep=sweep,
    )
    snippet = result.toml_snippet()
    assert f"{expected_key} = 100" in snippet
