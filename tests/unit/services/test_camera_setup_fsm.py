"""Tests for the per-camera setup FSM — M10-003."""
from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from smart_telescope.config import LiveAnalysisSpec
from smart_telescope.services.camera_setup_fsm import CameraSetupService
from smart_telescope.services.job_manager import JobManager

_SPEC = LiveAnalysisSpec(
    enabled=True, setup_exposure_s=0.01,
    tuning_frames=2, star_check_frames=3, star_count_min=3,
)


class _FakeCamera:
    def __init__(self):
        self.captures = 0

    def capture(self, exposure_s):
        self.captures += 1
        return SimpleNamespace(pixels=None, exposure_seconds=exposure_s, header={})


def _analyze_with_stars(stars):
    def fn(camera_info, frame, previous_star_state=None):
        return {
            "single_frame": {"stars_found": stars, "image_quality": "ok"},
            "recommendation": {"action": "keep"},
            "state": {"next_frame_index": 2},
        }
    return fn


def _camera_info_fn(camera, frame=None, binning=1):
    return {"exposure_s": 0.01, "gain": 101}


def _readiness(roles):
    return lambda: {"roles": roles}


_DETECTED_MAIN = {"main": {"status": "DETECTED", "sdk_index": 0}}


def _service(jm=None, camera=None, analyze_fn=None, roles=None, registry=None,
             focus_fn=None):
    return CameraSetupService(
        job_manager=jm or JobManager(),
        camera_provider=lambda role: camera if camera is not None else _FakeCamera(),
        readiness_snapshot=_readiness(roles if roles is not None else dict(_DETECTED_MAIN)),
        registry_provider=(lambda: registry) if registry is not None else None,
        analyze_fn=analyze_fn or _analyze_with_stars(5),
        camera_info_fn=_camera_info_fn,
        focus_fn=focus_fn,
    )


def _wait_phase(svc, role, phases, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        entry = svc.snapshot().get(role)
        if entry and entry["phase"] in phases:
            return entry
        time.sleep(0.01)
    pytest.fail(f"role {role!r} never reached {phases}; last={svc.snapshot().get(role)}")


def _run(svc):
    import smart_telescope.config as cfg
    with patch.object(cfg, "LIVE_ANALYSIS", _SPEC):
        svc.poll_once()
        return _wait_phase(svc, "main", {"READY", "DEGRADED", "IDLE"})


class TestPhases:
    def test_happy_path_reaches_ready(self):
        cam = _FakeCamera()
        entry = _run(_service(camera=cam))
        assert entry["phase"] == "READY"
        assert entry["stars_found"] == 5
        assert entry["exposure_s"] == 0.01
        assert entry["gain"] == 101
        assert entry["recommendation"] == {"action": "keep"}
        # Stars found during tuning → star check passes without extra frames.
        assert cam.captures == _SPEC.tuning_frames
        assert entry["frames_analyzed"] == _SPEC.tuning_frames
        # Non-focuser role (no registry) skips FOCUSING entirely.
        assert entry["focus_note"] is None

    def test_no_stars_reports_degraded_with_reason(self):
        cam = _FakeCamera()
        entry = _run(_service(camera=cam, analyze_fn=_analyze_with_stars(1)))
        assert entry["phase"] == "DEGRADED"
        assert "only 1 star(s) detected (min 3)" in entry["reason"]
        assert cam.captures == _SPEC.tuning_frames + _SPEC.star_check_frames

    def test_focuser_train_gets_focusing_phase_note(self):
        registry = SimpleNamespace(
            by_camera_role=lambda r: SimpleNamespace(has_focuser=True) if r == "main" else None,
        )
        entry = _run(_service(registry=registry))
        assert entry["phase"] == "READY"
        assert entry["focus_note"] == "coarse focus check pending (M10-006)"

    def test_injected_focus_fn_is_used(self):
        registry = SimpleNamespace(
            by_camera_role=lambda r: SimpleNamespace(has_focuser=True),
        )
        entry = _run(_service(registry=registry,
                              focus_fn=lambda cam, analysis: "focused to HFD 3.2"))
        assert entry["focus_note"] == "focused to HFD 3.2"

    def test_capture_failure_degrades(self):
        class Boom:
            def capture(self, exposure_s):
                raise RuntimeError("USB gone")
        entry = _run(_service(camera=Boom()))
        assert entry["phase"] == "DEGRADED"
        assert "USB gone" in entry["reason"]

    def test_analyzer_import_error_degrades_with_clear_reason(self):
        def missing(camera_info, frame, previous_star_state=None):
            raise ImportError("No module named 'smarttscope_live_analysis'")
        entry = _run(_service(analyze_fn=missing))
        assert entry["phase"] == "DEGRADED"
        assert "LiveAnalysis module unavailable" in entry["reason"]


class TestCameraErrors:
    # Pi hardware 2026-07-18: the guide-camera open failed with the bare
    # ToupTek HRESULT "-2147024726" (0x800700AA, ERROR_BUSY).
    def test_busy_hresult_stays_idle_for_retry_with_readable_reason(self):
        entry = self._svc_with_provider_error("-2147024726")
        assert entry["phase"] == "IDLE"
        assert "0x800700aa" in entry["reason"]
        assert "already in use" in entry["reason"]

    def test_non_busy_hresult_degrades_with_readable_reason(self):
        entry = self._svc_with_provider_error("-2147024891")
        assert entry["phase"] == "DEGRADED"
        assert "access denied" in entry["reason"]

    def test_plain_error_message_passes_through(self):
        entry = self._svc_with_provider_error("no device found")
        assert entry["phase"] == "DEGRADED"
        assert entry["reason"] == "camera unavailable: no device found"

    def test_busy_camera_recovers_once_released(self):
        import smart_telescope.config as cfg
        holder = {"busy": True}

        def provider(role):
            if holder["busy"]:
                raise RuntimeError("-2147024726")
            return _FakeCamera()

        svc = CameraSetupService(
            job_manager=JobManager(),
            camera_provider=provider,
            readiness_snapshot=_readiness(dict(_DETECTED_MAIN)),
            analyze_fn=_analyze_with_stars(5),
            camera_info_fn=_camera_info_fn,
        )
        with patch.object(cfg, "LIVE_ANALYSIS", _SPEC):
            svc.poll_once()
            entry = _wait_phase(svc, "main", {"IDLE"})
            assert "camera busy" in entry["reason"]
            holder["busy"] = False
            svc.poll_once()
            entry = _wait_phase(svc, "main", {"READY", "DEGRADED"})
        assert entry["phase"] == "READY"

    @staticmethod
    def _svc_with_provider_error(message):
        def provider(role):
            raise RuntimeError(message)
        svc = CameraSetupService(
            job_manager=JobManager(),
            camera_provider=provider,
            readiness_snapshot=_readiness(dict(_DETECTED_MAIN)),
            analyze_fn=_analyze_with_stars(5),
            camera_info_fn=_camera_info_fn,
        )
        import smart_telescope.config as cfg
        with patch.object(cfg, "LIVE_ANALYSIS", _SPEC):
            svc.poll_once()
            return _wait_phase(svc, "main", {"IDLE", "DEGRADED"})


class TestArbitration:
    def test_busy_camera_stays_idle_then_recovers_after_release(self):
        import smart_telescope.config as cfg
        jm = JobManager()
        blocker = jm.claim("autogain", {"camera:0"})
        svc = _service(jm=jm)
        with patch.object(cfg, "LIVE_ANALYSIS", _SPEC):
            svc.poll_once()
            entry = svc.snapshot()["main"]
            assert entry["phase"] == "IDLE"
            assert "camera busy" in entry["reason"]
            jm.release(blocker.job_id)
            svc.poll_once()
            entry = _wait_phase(svc, "main", {"READY", "DEGRADED"})
        assert entry["phase"] == "READY"

    def test_resources_released_after_completion(self):
        jm = JobManager()
        svc = _service(jm=jm)
        _run(svc)
        assert not jm.is_resource_held("camera:0")

    def test_terminal_phase_is_not_relaunched(self):
        import smart_telescope.config as cfg
        cam = _FakeCamera()
        svc = _service(camera=cam)
        _run(svc)
        captures = cam.captures
        with patch.object(cfg, "LIVE_ANALYSIS", _SPEC):
            svc.poll_once()
            time.sleep(0.05)
        assert cam.captures == captures


class TestConfigGates:
    def test_disabled_config_launches_nothing(self):
        import smart_telescope.config as cfg
        svc = _service()
        with patch.object(cfg, "LIVE_ANALYSIS",
                          LiveAnalysisSpec(enabled=False)):
            svc.poll_once()
        assert svc.snapshot() == {}

    def test_undetected_roles_are_skipped(self):
        import smart_telescope.config as cfg
        svc = _service(roles={"main": {"status": "MISSING", "sdk_index": None}})
        with patch.object(cfg, "LIVE_ANALYSIS", _SPEC):
            svc.poll_once()
        assert svc.snapshot() == {}
