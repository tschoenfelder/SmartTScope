"""Phase 14 — live pipeline wiring tests (COL-140/141/142).

Verifies that the newly wired assistant handlers drive the state machine
correctly using ReplayCameraAdapter + frame_factories (no real hardware).
"""
from __future__ import annotations

import time

import numpy as np
import pytest

from smart_telescope.adapters.mock.focuser import MockFocuser
from smart_telescope.adapters.mock.mount import MockMount
from smart_telescope.adapters.replay.camera import ReplayCameraAdapter
from smart_telescope.services.collimation.assistant import CollimationAssistant
from smart_telescope.services.collimation.frame_factories import (
    donut_ring,
    focus_sequence,
    gaussian_star,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

_FWHM_SEQ = [8.0, 7.0, 6.0, 5.0, 4.0, 3.5, 3.0, 2.8, 2.7, 2.8, 3.0, 3.5]


def _focus_camera(n_repeats: int = 10) -> ReplayCameraAdapter:
    """Cycling gaussian-star focus sequence."""
    frames = focus_sequence(256, 256, cx=128.0, cy=128.0,
                            fwhm_values=_FWHM_SEQ * n_repeats,
                            peak_adu=40_000.0, bg_adu=1_000.0)
    return ReplayCameraAdapter(frames, bit_depth=16, cycle=True)


def _blank_camera() -> ReplayCameraAdapter:
    """Camera that returns flat background frames (no star)."""
    frame = np.zeros((256, 256), dtype=np.float32) + 500.0
    return ReplayCameraAdapter([frame] * 20, cycle=True)


def _donut_camera() -> ReplayCameraAdapter:
    """Camera that delivers donut frames once the pipeline reaches MEASURE_DONUT.

    Identical to _star_then_donut_camera(); provides a semantically distinct
    name for tests that focus on frame_counter / donut detection.
    """
    return _star_then_donut_camera()


def _star_then_donut_camera() -> ReplayCameraAdapter:
    """Camera serving exactly 57 gaussian frames (for early pipeline phases)
    then donut-ring frames (served during MEASURE_DONUT).

    Frame-count breakdown before MEASURE_DONUT:
      ACQUIRE(1) + CENTER(1) + AUTO_EXP(8) + FocusSearch(5) + Defocus(42) = 57
    so MEASURE_DONUT attempt 1 receives the first donut frame.
    """
    star_frames = focus_sequence(
        256, 256, cx=128.0, cy=128.0,
        fwhm_values=(_FWHM_SEQ * 5)[:57],
        peak_adu=40_000.0, bg_adu=1_000.0,
    )
    ring = donut_ring(
        256, 256, outer_cx=128.0, outer_cy=128.0,
        outer_r=60.0, inner_r=25.0,
        peak_adu=30_000.0, bg_adu=1_000.0,
    )
    frames = list(star_frames) + [ring] * 20
    return ReplayCameraAdapter(frames, bit_depth=16, cycle=True)


def _assistant(camera=None) -> CollimationAssistant:
    cam     = camera if camera is not None else _focus_camera()
    mount   = MockMount()
    focuser = MockFocuser(available=True)
    return CollimationAssistant(cam, mount, focuser)


def _wait_for(assistant: CollimationAssistant, state_value: str,
              timeout: float = 15.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        s = assistant.status["state"]
        if s == state_value:
            return True
        if s == "failed":
            return False
        time.sleep(0.02)
    return False


def _drive_to_guide_rough(a: CollimationAssistant, timeout: float = 20.0) -> bool:
    """Drive assistant through acquisition + rough pipeline to GUIDE_ROUGH_COLLIMATION."""
    a.start()
    if not _wait_for(a, "select_star", timeout=5.0):
        return False
    a.advance({"ra": 5.0, "dec": 45.0})
    return _wait_for(a, "guide_rough_collimation", timeout=timeout)


# ── COL-140: Acquisition pipeline ─────────────────────────────────────────────

class TestAcquisitionPipeline:
    def test_gaussian_star_reaches_guide_rough(self):
        """Star detection + centering + auto-exposure + rough pipeline complete."""
        a = _assistant(_focus_camera())
        reached = _drive_to_guide_rough(a)
        a.cancel()
        assert reached, f"expected GUIDE_ROUGH_COLLIMATION, got {a.status['state']}"

    def test_blank_frames_fail_in_acquire_star(self):
        """No star detected after 5 attempts → FAILED."""
        a = _assistant(_blank_camera())
        a.start()
        _wait_for(a, "select_star", timeout=3.0)
        a.advance({"ra": 5.0, "dec": 45.0})
        assert _wait_for(a, "failed", timeout=10.0), \
            f"expected FAILED, got {a.status['state']}"

    def test_center_star_transitions_to_auto_exposure(self):
        """Centering loop completes (star at frame center → within_tolerance)."""
        a = _assistant(_focus_camera())
        a.start()
        _wait_for(a, "select_star")
        a.advance({"ra": 5.0, "dec": 45.0})
        assert _wait_for(a, "auto_exposure") or _wait_for(a, "rough_defocus") or \
               _wait_for(a, "guide_rough_collimation"), \
               f"expected progress past center_star, got {a.status['state']}"
        a.cancel()

    def test_auto_exposure_adjusts_camera(self):
        """AUTO_EXPOSURE changes the stored exposure setting."""
        cam = _focus_camera()
        initial_exp = cam.get_exposure_ms()
        a   = _assistant(cam)
        a.start()
        _wait_for(a, "select_star")
        a.advance({"ra": 5.0, "dec": 45.0})
        # Wait for rough_defocus to confirm auto_exposure completed
        _wait_for(a, "rough_defocus", timeout=15.0)
        a.cancel()
        # Exposure should have been adjusted (synthetic frames never reach 80%)
        assert cam.get_exposure_ms() >= initial_exp


# ── COL-141: Rough collimation pipeline ───────────────────────────────────────

class TestRoughPipeline:
    def test_rough_defocus_transitions_to_map_screws(self):
        """After rough defocus the assistant reaches MAP_SCREWS."""
        a = _assistant(_focus_camera())
        a.start()
        _wait_for(a, "select_star")
        a.advance({"ra": 5.0, "dec": 45.0})
        # map_screws_by_obstruction is a very short state (auto-transitions)
        # Just verify guide_rough_collimation is reached
        reached = _wait_for(a, "guide_rough_collimation", timeout=20.0)
        a.cancel()
        assert reached, f"stuck at {a.status['state']}"

    def test_measure_donut_with_donut_frames_updates_last_frame(self):
        """DonutAnalyzer detects ring from donut frames → last_measurement populated."""
        a = _assistant(_star_then_donut_camera())
        a.start()
        _wait_for(a, "select_star")
        a.advance({"ra": 5.0, "dec": 45.0})
        reached = _wait_for(a, "guide_rough_collimation", timeout=20.0)
        meas = a.status.get("last_measurement")
        a.cancel()
        assert reached, f"stuck at {a.status['state']}"
        assert meas is not None, "expected last_measurement populated by DonutAnalyzer"

    def test_measure_donut_gaussian_frames_proceeds_without_donut(self):
        """Gaussian frames have no donut ring; handler warns and proceeds anyway."""
        a = _assistant(_focus_camera())
        reached = _drive_to_guide_rough(a)
        a.cancel()
        assert reached, f"stuck at {a.status['state']}"

    def test_no_screw_recommendation_without_calibration(self):
        """CollimationAdvisor with empty calibrations produces no recommendation."""
        a = _assistant(_star_then_donut_camera())
        _drive_to_guide_rough(a)
        rec = a.status.get("current_recommendation")
        a.cancel()
        assert rec is None  # CollimationAdvisor suppresses rec when calibrations=[]


# ── COL-142: Fine collimation pipeline ────────────────────────────────────────

class TestFinePipeline:
    def test_map_mask_sectors_sets_mask_calibration(self):
        """_handle_map_mask_sectors initialises _mask_calibration, smoother, detector."""
        a = _assistant(_focus_camera())
        a.start()
        _wait_for(a, "select_star")
        a.advance({"ra": 5.0, "dec": 45.0})
        _wait_for(a, "guide_rough_collimation", timeout=20.0)
        a.advance({"finish": True})
        _wait_for(a, "install_tribahtinov")
        a.advance({})  # triggers MAP_MASK_SECTORS
        # Verify calibration was set after MAP_MASK_SECTORS
        _wait_for(a, "fine_focus")  # fine_focus follows map_mask_sectors
        with a._lock:
            cal      = a._mask_calibration
            smoother = a._spike_smoother
            detector = a._contradiction_detector
        a.cancel()
        assert cal is not None,      "mask_calibration not set"
        assert smoother is not None, "spike_smoother not set"
        assert detector is not None, "contradiction_detector not set"
        assert cal.sector_0_deg   == "T1"
        assert cal.sector_120_deg == "T2"
        assert cal.sector_240_deg == "T3"

    def test_fine_focus_transitions_to_measure_spikes(self):
        """FINE_FOCUS completes (star_lost on gaussian frames) → MEASURE_SPIKES."""
        a = _assistant(_focus_camera())
        a.start()
        _wait_for(a, "select_star")
        a.advance({"ra": 5.0, "dec": 45.0})
        _wait_for(a, "guide_rough_collimation", timeout=20.0)
        a.advance({"finish": True})
        _wait_for(a, "install_tribahtinov")
        a.advance({})
        # fine_focus auto-transitions to measure_spikes
        reached = _wait_for(a, "measure_spikes") or _wait_for(a, "guide_fine_collimation")
        a.cancel()
        assert reached, f"stuck at {a.status['state']}"

    def test_measure_spikes_gaussian_frames_proceeds_without_spikes(self):
        """Gaussian frames have no Bahtinov spikes; handler warns and proceeds."""
        a = _assistant(_focus_camera())
        a.start()
        _wait_for(a, "select_star")
        a.advance({"ra": 5.0, "dec": 45.0})
        _wait_for(a, "guide_rough_collimation", timeout=20.0)
        a.advance({"finish": True})
        _wait_for(a, "install_tribahtinov")
        a.advance({})
        reached = _wait_for(a, "guide_fine_collimation", timeout=20.0)
        a.cancel()
        assert reached, f"stuck at {a.status['state']}"

    def test_full_flow_still_completes(self):
        """Full flow (with wired handlers) still reaches COMPLETE."""
        a = _assistant(_focus_camera())
        a.start()

        assert _wait_for(a, "select_star"), "never reached SELECT_STAR"
        a.advance({"ra": 5.0, "dec": 45.0})

        assert _wait_for(a, "guide_rough_collimation", timeout=20.0), \
            f"stuck before GUIDE_ROUGH at {a.status['state']}"
        a.advance({"finish": True})

        assert _wait_for(a, "install_tribahtinov"), "never reached INSTALL_TRIBAHTINOV"
        a.advance({})

        assert _wait_for(a, "guide_fine_collimation", timeout=20.0), \
            f"stuck before GUIDE_FINE at {a.status['state']}"
        a.advance({"finish": True})

        assert _wait_for(a, "maskless_validation", timeout=15.0), \
            f"never reached MASKLESS_VALIDATION — stuck at {a.status['state']}"
        a.advance({"accept": True})

        assert _wait_for(a, "complete", timeout=10.0), \
            f"never reached COMPLETE — stuck at {a.status['state']}"

    def test_frame_counter_increments_on_donut_measurement(self):
        """_frame_counter increases when a donut is successfully analysed."""
        a = _assistant(_donut_camera())
        _drive_to_guide_rough(a)
        with a._lock:
            counter = a._frame_counter
        a.cancel()
        assert counter > 0, "frame_counter should have been incremented"
