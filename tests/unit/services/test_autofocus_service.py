"""Tests for AutofocusService (M7-007 / AF-001..AF-005 / TEST-004)."""

from __future__ import annotations

import numpy as np
import pytest

from smart_telescope.services.autofocus_service import (
    AutofocusRecommendation,
    AutofocusService,
    FocusQuality,
)


def _frame_with_hfd(hfd_target: float, size: int = 64) -> np.ndarray:
    """Create a synthetic frame whose Half-Flux Diameter approximates hfd_target."""
    pixels = np.zeros((size, size), dtype=np.float32)
    cx, cy = size // 2, size // 2
    radius = max(1, hfd_target / 2.0)
    for y in range(size):
        for x in range(size):
            r = np.hypot(x - cx, y - cy)
            if r <= radius:
                pixels[y, x] = float(1000.0 * (1.0 - r / radius))
    return pixels


def _blank_frame(size: int = 64) -> np.ndarray:
    return np.zeros((size, size), dtype=np.float32)


# ── TEST-004-1: not enough samples → keep moving ──────────────────────────────

def test_keep_moving_with_few_samples():
    """With fewer than 3 valid samples, analyze() always recommends a move."""
    svc = AutofocusService(step_size=20)
    px = _frame_with_hfd(30.0)
    result = svc.analyze(px, current_position=1000)
    assert result.autofocus_finished is False
    assert result.focus_movement_steps != 0


# ── TEST-004-2: out-of-focus frame → UNKNOWN quality, still moves ─────────────

def test_blank_frame_returns_unknown_quality():
    """A blank frame (no signal) returns focus_quality=UNKNOWN."""
    svc = AutofocusService()
    result = svc.analyze(_blank_frame(), current_position=1000)
    assert result.focus_quality == FocusQuality.UNKNOWN
    # UNKNOWN frames are not counted — service should still recommend a move
    assert result.autofocus_finished is False


# ── TEST-004-3: at best position → finished ───────────────────────────────────

def test_finishes_at_best_position():
    """When current position equals best position and HFD is clearly best, finish."""
    svc = AutofocusService(step_size=20, quality_threshold_hfd=10.0)
    # Feed improving sequence: HFD decreasing toward best at pos=1060
    positions = [1000, 1020, 1040, 1060, 1080, 1100]
    hfds      = [ 40,    30,   20,   10,   20,   35 ]
    result = None
    for pos, hfd in zip(positions, hfds):
        result = svc.analyze(_frame_with_hfd(float(hfd)), current_position=pos)
    assert result is not None
    assert result.autofocus_finished is True


# ── TEST-004-4: reset clears history ─────────────────────────────────────────

def test_reset_clears_history():
    """reset() discards all samples so the service starts fresh."""
    svc = AutofocusService(step_size=20)
    for pos in range(1000, 1120, 20):
        svc.analyze(_frame_with_hfd(10.0), current_position=pos)

    svc.reset()
    result = svc.analyze(_frame_with_hfd(10.0), current_position=1000)
    assert result.autofocus_finished is False  # only 1 sample after reset


# ── TEST-004-5: AF-005 mount offset returned as pixels ────────────────────────

def test_mount_offset_returned_as_pixels():
    """analyze() returns target_offset_x_px / target_offset_y_px (not RA/DEC)."""
    svc = AutofocusService()
    result = svc.analyze(_frame_with_hfd(20.0), current_position=1000)
    # Values are float pixel offsets (may be 0.0 when no correction needed)
    assert isinstance(result.target_offset_x_px, float)
    assert isinstance(result.target_offset_y_px, float)


# ── diagnostics populated ─────────────────────────────────────────────────────

def test_diagnostics_include_current_position():
    """diagnostics.current_focus_position_if_known is set on every call."""
    svc = AutofocusService()
    result = svc.analyze(_frame_with_hfd(20.0), current_position=1234)
    assert result.diagnostics.current_focus_position_if_known == 1234
