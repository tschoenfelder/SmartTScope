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


def _make_minimal_assistant(guiding_service=None, guide_cameras=None, frame_archive=None):
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
        frame_archive=frame_archive,
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


def test_frame_archive_property_returns_injected_archive():
    archive = MagicMock()
    assistant = _make_minimal_assistant(frame_archive=archive)
    assert assistant.frame_archive is archive


def test_no_frame_archive_property_is_none():
    assistant = _make_minimal_assistant()
    assert assistant.frame_archive is None


def test_archive_new_session_called_on_start():
    from smart_telescope.services.collimation.assistant import CollimationAssistant
    archive = MagicMock()
    a = CollimationAssistant(
        camera=MagicMock(
            **{"get_bit_depth.return_value": 16,
               "get_exposure_ms.return_value": 100.0,
               "get_gain.return_value": 100}
        ),
        mount=MagicMock(),
        focuser=MagicMock(),
        frame_archive=archive,
    )
    a.start()
    archive.new_session.assert_called_once()


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


# ── Status measurement metrics ────────────────────────────────────────────────

def _make_frame_measurement(donut=None, spike=None, star=None):
    from smart_telescope.domain.collimation.models import FrameMeasurement
    return FrameMeasurement(
        frame_index=1,
        captured_at="2026-01-01T00:00:00+00:00",
        exposure_s=2.0,
        gain=100,
        star=star,
        donut=donut,
        spike=spike,
    )


def _make_donut_measurement(error_x=5.0, error_y=3.0, outer_r=80.0):
    from smart_telescope.domain.collimation.models import DonutMeasurement, CircleEllipseFit
    import math
    outer = CircleEllipseFit(center_x=100.0, center_y=100.0, radius_x=outer_r, radius_y=outer_r)
    inner = CircleEllipseFit(
        center_x=100.0 + error_x, center_y=100.0 + error_y,
        radius_x=30.0, radius_y=30.0,
    )
    mag = math.hypot(error_x, error_y)
    return DonutMeasurement(
        outer_ring=outer, inner_hole=inner,
        error_x_px=error_x, error_y_px=error_y,
        error_magnitude_px=mag,
        error_angle_deg=0.0,
        confidence=0.9,
    )


def _make_spike_measurement(focus_error=1.2, offset=3.0):
    from smart_telescope.domain.collimation.models import SpikeMeasurement
    return SpikeMeasurement(
        focus_error_px=focus_error,
        crossing_error_rms_px=0.8,
        crossing_point_x=200.0, crossing_point_y=200.0,
        reference_center_x=200.0, reference_center_y=200.0,
        offset_from_ref_px=offset,
        confidence=0.85,
    )


def test_status_last_measurement_none_when_no_frame():
    assistant = _make_minimal_assistant()
    s = assistant.status
    assert s["last_measurement"] is None


def test_status_last_measurement_donut_fields():
    assistant = _make_minimal_assistant()
    assistant._last_frame = _make_frame_measurement(donut=_make_donut_measurement())
    s = assistant.status
    meas = s["last_measurement"]
    assert meas is not None
    assert meas["measurement_type"] == "donut"
    assert "donut" in meas
    d = meas["donut"]
    assert d["error_x_px"] == pytest.approx(5.0)
    assert d["error_y_px"] == pytest.approx(3.0)
    assert d["error_magnitude_px"] == pytest.approx(5.831, abs=0.01)
    assert 0 < d["error_fraction"] < 1
    assert d["outer_radius_px"] == pytest.approx(80.0)
    assert d["confidence"] == pytest.approx(0.9)
    assert isinstance(d["is_collimated"], bool)
    assert "spikes" not in meas
    assert "star" not in meas


def test_status_last_measurement_spikes_fields():
    assistant = _make_minimal_assistant()
    assistant._last_frame = _make_frame_measurement(spike=_make_spike_measurement())
    s = assistant.status
    meas = s["last_measurement"]
    assert meas["measurement_type"] == "spikes"
    assert "spikes" in meas
    sp = meas["spikes"]
    assert sp["focus_error_px"] == pytest.approx(1.2)
    assert sp["offset_from_ref_px"] == pytest.approx(3.0)
    assert sp["crossing_error_rms_px"] == pytest.approx(0.8)
    assert isinstance(sp["is_in_focus"], bool)
    assert "donut" not in meas


def test_status_last_measurement_star_fields():
    from smart_telescope.domain.collimation.models import StarMeasurement
    star = StarMeasurement(
        center_x=100.0, center_y=100.0, fwhm_px=3.5, peak_adu=50000.0,
        total_flux=1e6, snr=45.0, confidence=0.95,
    )
    assistant = _make_minimal_assistant()
    assistant._last_frame = _make_frame_measurement(star=star)
    s = assistant.status
    meas = s["last_measurement"]
    assert meas["measurement_type"] == "star"
    assert "star" in meas
    assert meas["star"]["fwhm_px"] == pytest.approx(3.5)
    assert meas["star"]["snr"] == pytest.approx(45.0)
