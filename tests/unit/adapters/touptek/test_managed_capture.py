"""Unit tests for SmartTouptekCamera's still-image flag on capture (M10-056).

A real Pi server.log confirmed the guide camera (GPCMOS02000KPA, the only
camera using "snap" capture mode) never fires _EVENT_STILLIMAGE for its
software-triggered captures -- only _EVENT_IMAGE -- which meant
_pull_pixels() always got still=False and pulled from the wrong buffer
(mean/percentile ADU identical across 30+ frames despite exposure/gain
changes). _capture_raw() must now force still=True whenever capture_mode is
"snap", regardless of which event actually fired.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from smart_telescope.adapters.touptek.managed import (
    _EVENT_IMAGE,
    _EVENT_STILLIMAGE,
    SmartTouptekCamera,
)


def _ready_camera(capture_mode: str, fired_event: int) -> SmartTouptekCamera:
    cam = SmartTouptekCamera(capture_mode=capture_mode)
    cam._cam = MagicMock()
    cam._tc = MagicMock()

    def _trigger(_value: int) -> None:
        cam._last_event = fired_event
        cam._frame_ready.set()

    cam._cam.Trigger.side_effect = _trigger
    return cam


class TestCaptureRawStillFlag:
    def test_snap_mode_forces_still_true_even_on_event_image(self) -> None:
        cam = _ready_camera(capture_mode="snap", fired_event=_EVENT_IMAGE)
        with patch.object(cam, "_pull_pixels", return_value="pixels") as mock_pull:
            cam._capture_raw(timeout_s=1.0)
        mock_pull.assert_called_once_with(still=True)

    def test_snap_mode_still_true_on_event_stillimage_too(self) -> None:
        cam = _ready_camera(capture_mode="snap", fired_event=_EVENT_STILLIMAGE)
        with patch.object(cam, "_pull_pixels", return_value="pixels") as mock_pull:
            cam._capture_raw(timeout_s=1.0)
        mock_pull.assert_called_once_with(still=True)

    def test_non_snap_mode_still_follows_event_type(self) -> None:
        cam = _ready_camera(capture_mode="indi-stream-trigger", fired_event=_EVENT_IMAGE)
        with patch.object(cam, "_pull_pixels", return_value="pixels") as mock_pull:
            cam._capture_raw(timeout_s=1.0)
        mock_pull.assert_called_once_with(still=False)

    def test_non_snap_mode_still_true_on_stillimage_event(self) -> None:
        cam = _ready_camera(capture_mode="indi-stream-trigger", fired_event=_EVENT_STILLIMAGE)
        with patch.object(cam, "_pull_pixels", return_value="pixels") as mock_pull:
            cam._capture_raw(timeout_s=1.0)
        mock_pull.assert_called_once_with(still=True)
