"""Tests for CollimationAssistant guiding integration."""
import pytest
from smart_telescope.domain.collimation.config import CollimationConfig


def test_collimation_config_guiding_defaults():
    cfg = CollimationConfig.from_dict({})
    assert cfg.guiding_camera_role == "guide"
    assert cfg.guiding_exposure_s == 2.0
    assert cfg.guiding_cadence_s == 3.0


def test_collimation_config_guiding_from_toml():
    cfg = CollimationConfig.from_dict({
        "guiding_camera_role": "oag",
        "guiding_exposure_s": 1.5,
        "guiding_cadence_s": 2.0,
    })
    assert cfg.guiding_camera_role == "oag"
    assert cfg.guiding_exposure_s == 1.5
    assert cfg.guiding_cadence_s == 2.0


import threading
import time
from unittest.mock import MagicMock, call, patch


def _make_mock_guiding_service():
    svc = MagicMock()
    svc.status.return_value = MagicMock(
        state="idle", rms_px=0.0, last_pulse=None
    )
    svc.status.return_value.to_dict.return_value = {
        "state": "idle", "rms_px": 0.0, "last_pulse": None,
    }
    return svc


def _make_minimal_assistant(guiding_service=None, guide_cameras=None):
    from smart_telescope.services.collimation.assistant import CollimationAssistant
    cam = MagicMock()
    cam.get_bit_depth.return_value = 16
    cam.get_exposure_ms.return_value = 100.0
    cam.get_gain.return_value = 100
    mount = MagicMock()
    focuser = MagicMock()
    return CollimationAssistant(
        camera=cam,
        mount=mount,
        focuser=focuser,
        guiding_service=guiding_service,
        guide_cameras=guide_cameras or {},
    )


def test_assistant_accepts_guiding_service_kwarg():
    svc = _make_mock_guiding_service()
    assistant = _make_minimal_assistant(guiding_service=svc)
    assert assistant is not None


def test_no_guiding_service_does_not_crash():
    assistant = _make_minimal_assistant(guiding_service=None)
    assert assistant is not None


def test_status_includes_guiding_dict_when_service_present():
    svc = _make_mock_guiding_service()
    assistant = _make_minimal_assistant(guiding_service=svc)
    s = assistant.status
    assert "guiding" in s
    assert s["guiding"]["available"] is True


def test_status_guiding_unavailable_when_no_service():
    assistant = _make_minimal_assistant(guiding_service=None)
    s = assistant.status
    assert s["guiding"]["available"] is False


def test_guiding_stops_when_run_exits():
    """Verify _stop_guiding() is called when the background thread finishes."""
    svc = _make_mock_guiding_service()
    svc.status.return_value.state = "running"

    from smart_telescope.services.collimation.assistant import CollimationAssistant
    cam = MagicMock()
    cam.get_bit_depth.return_value = 16
    cam.get_exposure_ms.return_value = 100.0
    cam.get_gain.return_value = 100
    mount = MagicMock()
    mount.goto.side_effect = RuntimeError("no mount")  # causes FAILED immediately
    focuser = MagicMock()

    assistant = CollimationAssistant(
        camera=cam, mount=mount, focuser=focuser,
        guiding_service=svc, guide_cameras={"guide": MagicMock()},
    )
    assistant.start()
    time.sleep(0.3)  # let background thread run until FAILED

    # stop() is called in finally block of _run()
    svc.stop.assert_called()


def test_archive_config_defaults():
    cfg = CollimationConfig.from_dict({})
    assert cfg.archive.enabled is False
    assert cfg.archive.archive_dir == ""
    assert cfg.archive.max_frames_per_session == 50


def test_archive_config_from_dict():
    cfg = CollimationConfig.from_dict({
        "archive": {
            "enabled": True,
            "archive_dir": "/tmp/test_archive",
            "max_frames_per_session": 10,
        }
    })
    assert cfg.archive.enabled is True
    assert cfg.archive.archive_dir == "/tmp/test_archive"
    assert cfg.archive.max_frames_per_session == 10
