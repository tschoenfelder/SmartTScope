"""Unit tests for auto_stretch."""
from typing import Any

import numpy as np

from smart_telescope.domain.stretch import auto_stretch


def _arr(*values: float, shape: tuple[int, int] = (4, 4)) -> np.ndarray[Any, np.dtype[Any]]:
    return np.array(values, dtype=np.float32).reshape(shape)


class TestAutoStretch:
    def test_output_dtype_is_uint8(self) -> None:
        pixels = np.random.default_rng(0).uniform(0, 65535, (10, 10)).astype(np.float32)
        result = auto_stretch(pixels)
        assert result.dtype == np.uint8

    def test_output_shape_matches_input(self) -> None:
        pixels = np.zeros((48, 64), dtype=np.float32)
        result = auto_stretch(pixels)
        assert result.shape == (48, 64)

    def test_uniform_array_returns_black(self) -> None:
        pixels = np.full((10, 10), 1000.0, dtype=np.float32)
        result = auto_stretch(pixels)
        assert np.all(result == 0)

    def test_zero_array_returns_black(self) -> None:
        pixels = np.zeros((8, 8), dtype=np.float32)
        result = auto_stretch(pixels)
        assert np.all(result == 0)

    def test_bright_peak_clips_to_255(self) -> None:
        rng = np.random.default_rng(1)
        pixels = rng.uniform(100, 1000, (50, 50)).astype(np.float32)
        # Plant a bright pixel well above p99.5
        pixels[25, 25] = 1_000_000.0
        result = auto_stretch(pixels)
        assert result[25, 25] == 255

    def test_dark_well_clips_to_0(self) -> None:
        rng = np.random.default_rng(2)
        pixels = rng.uniform(500, 1500, (50, 50)).astype(np.float32)
        pixels[10, 10] = -1_000_000.0
        result = auto_stretch(pixels)
        assert result[10, 10] == 0

    def test_linear_range_maps_correctly(self) -> None:
        # Linearly spaced values: after stretch, extremes should be ~0 and ~255
        pixels = np.linspace(0.0, 1000.0, 100 * 100, dtype=np.float32).reshape(100, 100)
        result = auto_stretch(pixels)
        # The 0.5th percentile maps to 0; 99.5th maps to 255
        # Values in between should be monotonically increasing
        flat = result.flatten()
        assert flat[0] == 0
        assert flat[-1] == 255
        assert np.all(np.diff(flat.astype(np.int16)) >= 0)

    def test_values_stay_within_0_255(self) -> None:
        rng = np.random.default_rng(3)
        pixels = rng.exponential(scale=500, size=(100, 100)).astype(np.float32)
        result = auto_stretch(pixels)
        assert result.min() >= 0
        assert result.max() <= 255

    def test_float64_input_accepted(self) -> None:
        pixels = np.random.default_rng(4).uniform(0, 1000, (20, 20))  # float64
        result = auto_stretch(pixels)
        assert result.dtype == np.uint8

    def test_realistic_sky_frame_has_full_dynamic_range(self) -> None:
        rng = np.random.default_rng(5)
        # Sky background + a few bright stars
        pixels = rng.normal(loc=800, scale=30, size=(200, 200)).astype(np.float32)
        pixels[50, 50] = 60_000.0   # bright star
        pixels[100, 100] = 45_000.0
        result = auto_stretch(pixels)
        # Should use most of the 0–255 range
        assert result.max() == 255
        assert result.min() == 0
