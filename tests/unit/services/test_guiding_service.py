import time

import numpy as np
import pytest
from astropy.io import fits

from smart_telescope.domain.guiding import GuideSourceHealth
from smart_telescope.services.guiding_service import GuidingService, GuidingStatus
from smart_telescope.services.guide_measurement import CentroidConfig, GuideControllerConfig


def _mock_camera_with_star():
    """Returns a MockCamera that captures a stable star frame."""
    from smart_telescope.adapters.mock.camera import MockCamera
    cam = MockCamera()
    cam.connect()
    return cam


def test_guiding_service_starts_and_produces_status():
    svc = GuidingService.from_config(
        primary_role="guide",
        allow_fallback=False,
        fallback_after_bad_frames=3,
        max_frame_age_s=2.0,
        centroid_config=CentroidConfig(roi_px=16, min_peak_snr=1.0),
        controller_config=GuideControllerConfig(),
        measure_only=True,
    )
    cam = _mock_camera_with_star()
    svc.start({"guide": cam}, exposure_s=0.01, cadence_s=0.05)
    time.sleep(0.4)
    status = svc.status()
    svc.stop()

    assert status.state == "running"
    assert "guide" in status.sources


def test_guiding_service_idle_after_stop():
    svc = GuidingService.from_config(
        primary_role="guide",
        allow_fallback=False,
        fallback_after_bad_frames=3,
        max_frame_age_s=2.0,
        centroid_config=CentroidConfig(),
        controller_config=GuideControllerConfig(),
        measure_only=True,
    )
    cam = _mock_camera_with_star()
    svc.start({"guide": cam}, exposure_s=0.01, cadence_s=0.05)
    time.sleep(0.1)
    svc.stop()

    assert svc.status().state == "idle"


def test_guiding_service_double_start_is_noop():
    svc = GuidingService.from_config(
        primary_role="guide",
        allow_fallback=False,
        fallback_after_bad_frames=3,
        max_frame_age_s=2.0,
        centroid_config=CentroidConfig(),
        controller_config=GuideControllerConfig(),
        measure_only=True,
    )
    cam = _mock_camera_with_star()
    svc.start({"guide": cam}, exposure_s=0.01, cadence_s=0.05)
    svc.start({"guide": cam}, exposure_s=0.01, cadence_s=0.05)  # should not crash
    svc.stop()
    assert svc.status().state == "idle"


def test_guiding_status_to_dict():
    status = GuidingStatus()
    d = status.to_dict()
    assert d["state"] == "idle"
    assert "sources" in d
    assert "latest_pulses" in d
