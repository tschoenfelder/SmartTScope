"""Integration tests for CollimationAssistant with replay hardware — COL-131.

Tests that the state machine progresses correctly through the full collimation
workflow using mock hardware and the replay camera adapter.
"""
from __future__ import annotations

import time

import pytest

from smart_telescope.adapters.mock.focuser import MockFocuser
from smart_telescope.adapters.mock.mount import MockMount
from smart_telescope.adapters.replay.camera import ReplayCameraAdapter
from smart_telescope.services.collimation.assistant import CollimationAssistant
from smart_telescope.services.collimation.frame_factories import (
    focus_sequence,
    gaussian_star,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

_FWHM_SEQUENCE = [8.0, 7.0, 6.0, 5.0, 4.0, 3.5, 3.0, 2.8, 2.7, 2.8, 3.0, 3.5]


def _focus_camera(cycle: bool = True) -> ReplayCameraAdapter:
    """Replay camera with a gaussian star focus sequence."""
    frames = focus_sequence(256, 256, cx=128.0, cy=128.0,
                            fwhm_values=_FWHM_SEQUENCE * 5,
                            peak_adu=40_000.0, bg_adu=1_000.0)
    return ReplayCameraAdapter(frames, bit_depth=16, cycle=cycle)


def _assistant(camera=None) -> CollimationAssistant:
    cam     = camera if camera is not None else _focus_camera()
    mount   = MockMount()
    focuser = MockFocuser(available=True)
    return CollimationAssistant(cam, mount, focuser)


def _wait_for(assistant: CollimationAssistant, state_value: str,
              timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if assistant.status["state"] == state_value:
            return True
        time.sleep(0.02)
    return False


def _run_full_flow(assistant: CollimationAssistant, timeout: float = 10.0) -> bool:
    """Drive the assistant through the happy-path flow.

    Returns True if COMPLETE is reached within *timeout* seconds.
    """
    assistant.start()

    if not _wait_for(assistant, "select_star", timeout):
        return False
    assistant.advance({"ra": 5.0, "dec": 45.0})

    if not _wait_for(assistant, "guide_rough_collimation", timeout):
        return False
    assistant.advance({"finish": True})

    if not _wait_for(assistant, "install_tribahtinov", timeout):
        return False
    assistant.advance({})

    if not _wait_for(assistant, "guide_fine_collimation", timeout):
        return False
    assistant.advance({"finish": True})

    # FINAL_REFOCUS: wired algorithm — may take a few calls
    if not _wait_for(assistant, "maskless_validation", timeout=10.0):
        return False
    assistant.advance({"accept": True})

    return _wait_for(assistant, "complete", timeout)


# ── Start / stop ──────────────────────────────────────────────────────────────

class TestStartStop:
    def test_initial_state_is_idle(self):
        a = _assistant()
        assert a.status["state"] == "idle"

    def test_start_transitions_out_of_idle(self):
        a = _assistant()
        a.start()
        time.sleep(0.1)
        assert a.status["state"] != "idle"
        a.cancel()

    def test_start_twice_raises(self):
        a = _assistant()
        a.start()
        _wait_for(a, "select_star")
        with pytest.raises(RuntimeError):
            a.start()
        a.cancel()

    def test_cancel_resets_to_idle(self):
        a = _assistant()
        a.start()
        _wait_for(a, "select_star")
        a.cancel()
        time.sleep(0.1)
        assert a.status["state"] == "idle"

    def test_retry_after_complete(self):
        a = _assistant()
        assert _run_full_flow(a)
        a.retry()
        assert a.status["state"] == "idle"


# ── Full happy-path flow ──────────────────────────────────────────────────────

class TestFullFlow:
    def test_reaches_complete(self):
        a = _assistant()
        assert _run_full_flow(a), "expected COMPLETE"

    def test_state_sequence_passes_through_user_wait_states(self):
        a = _assistant()
        a.start()

        assert _wait_for(a, "select_star"), "never reached SELECT_STAR"
        a.advance({"ra": 5.0, "dec": 45.0})

        assert _wait_for(a, "guide_rough_collimation"), "never reached GUIDE_ROUGH"
        a.advance({"finish": True})

        assert _wait_for(a, "install_tribahtinov"), "never reached INSTALL_TRIBAHTINOV"
        a.advance({})

        assert _wait_for(a, "guide_fine_collimation"), "never reached GUIDE_FINE"
        a.advance({"finish": True})

        assert _wait_for(a, "maskless_validation", timeout=10.0), \
            f"never reached MASKLESS_VALIDATION — stuck at {a.status['state']}"
        a.advance({"accept": True})

        assert _wait_for(a, "complete"), "never reached COMPLETE"

    def test_status_is_not_terminal_during_flow(self):
        a = _assistant()
        a.start()
        _wait_for(a, "select_star")
        assert not a.status.get("is_terminal")
        a.cancel()

    def test_report_contains_telescope_profile(self):
        a = _assistant()
        assert _run_full_flow(a)
        report = a.report
        assert "telescope_profile" in report

    def test_report_contains_overall_status(self):
        a = _assistant()
        assert _run_full_flow(a)
        report = a.report
        assert "overall_status" in report


# ── Advance validation ────────────────────────────────────────────────────────

class TestAdvance:
    def test_advance_from_non_wait_state_raises(self):
        a = _assistant()
        a.start()
        _wait_for(a, "select_star")
        a.advance({"ra": 5.0, "dec": 45.0})
        _wait_for(a, "guide_rough_collimation")
        # after advancing select_star we're in workflow states, not wait
        # advance from guide_rough_collimation is valid — test something else:
        # try advancing from idle before start
        a2 = _assistant()
        with pytest.raises(RuntimeError):
            a2.advance({"ra": 1.0, "dec": 1.0})
        a.cancel()

    def test_select_star_without_coordinates_stays_in_state(self):
        a = _assistant()
        a.start()
        _wait_for(a, "select_star")
        # advance with no ra/dec — handler should stay in SELECT_STAR
        a.advance({})
        time.sleep(0.1)
        assert a.status["state"] == "select_star"
        a.cancel()

    def test_maskless_validation_accept_false_returns_to_fine(self):
        a = _assistant()
        a.start()
        _wait_for(a, "select_star")
        a.advance({"ra": 5.0, "dec": 45.0})
        _wait_for(a, "guide_rough_collimation")
        a.advance({"finish": True})
        _wait_for(a, "install_tribahtinov")
        a.advance({})
        _wait_for(a, "guide_fine_collimation")
        a.advance({"finish": True})
        _wait_for(a, "maskless_validation", timeout=10.0)
        a.advance({"accept": False})
        assert _wait_for(a, "guide_fine_collimation"), \
            f"expected GUIDE_FINE after reject, got {a.status['state']}"
        a.cancel()


# ── Pause / resume ────────────────────────────────────────────────────────────

class TestPauseResume:
    def test_pause_sets_paused_state(self):
        a = _assistant()
        a.start()
        _wait_for(a, "select_star")
        a.pause()
        assert a.status["state"] == "paused"
        a.cancel()

    def test_resume_restores_previous_state(self):
        a = _assistant()
        a.start()
        _wait_for(a, "select_star")
        a.pause()
        a.resume()
        assert a.status["state"] == "select_star"
        a.cancel()

    def test_is_paused_flag_in_status(self):
        a = _assistant()
        a.start()
        _wait_for(a, "select_star")
        a.pause()
        assert a.status.get("is_paused") is True
        a.cancel()


# ── Final refocus wiring ──────────────────────────────────────────────────────

class TestFinalRefocusWiring:
    """Verify that _handle_final_refocus actually runs the algorithm."""

    def test_final_refocus_records_focus_status(self):
        a = _assistant()
        assert _run_full_flow(a)
        report = a.report
        # The wired handler should have set initial/final FWHM
        assert report.get("initial_focus_fwhm_px") is not None

    def test_final_refocus_transitions_to_maskless_validation(self):
        a = _assistant()
        a.start()
        _wait_for(a, "select_star")
        a.advance({"ra": 5.0, "dec": 45.0})
        _wait_for(a, "guide_rough_collimation")
        a.advance({"finish": True})
        _wait_for(a, "install_tribahtinov")
        a.advance({})
        _wait_for(a, "guide_fine_collimation")
        a.advance({"finish": True})
        reached = _wait_for(a, "maskless_validation", timeout=10.0)
        assert reached, f"FINAL_REFOCUS did not reach MASKLESS_VALIDATION; state={a.status['state']}"
        a.cancel()
