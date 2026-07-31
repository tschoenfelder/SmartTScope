"""Unit tests for SmartTouptekCamera's frame-pull implementation (M10-060).

M10-056 tried forcing still=True unconditionally for "snap" mode, reasoning
that the guide camera (GPCMOS02000KPA) never fires _EVENT_STILLIMAGE for its
software-triggered captures. A real Pi log proved that hypothesis WRONG:
PullImageV4(bStill=1) failed on every single guide-camera capture with SDK
error -2147483638 (0x8000000A). M10-057 reverted to depending on the fired
event (still=False in practice), but the frozen-frame bug (mean/percentile
ADU identical across frames) stayed open — PullImageV4 was never the right
API for this camera regardless of the still flag, since it's driven by
Trigger(1) exactly like every "indi-stream-trigger" camera. M10-060 removes
the separate "snap" pull path entirely: every capture_mode now pulls frames
via the same PullImageWithRowPitchV2 call.
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


class TestCaptureRawUnifiedPull:
    def test_snap_mode_calls_pull_pixels_with_no_args(self) -> None:
        cam = _ready_camera(capture_mode="snap", fired_event=_EVENT_IMAGE)
        with patch.object(cam, "_pull_pixels", return_value="pixels") as mock_pull:
            cam._capture_raw(timeout_s=1.0)
        mock_pull.assert_called_once_with()

    def test_stream_trigger_mode_calls_pull_pixels_with_no_args(self) -> None:
        cam = _ready_camera(capture_mode="indi-stream-trigger", fired_event=_EVENT_IMAGE)
        with patch.object(cam, "_pull_pixels", return_value="pixels") as mock_pull:
            cam._capture_raw(timeout_s=1.0)
        mock_pull.assert_called_once_with()

    def test_stillimage_event_does_not_change_pull_call(self) -> None:
        # Whichever event fired must no longer influence how pixels are pulled.
        cam = _ready_camera(capture_mode="snap", fired_event=_EVENT_STILLIMAGE)
        with patch.object(cam, "_pull_pixels", return_value="pixels") as mock_pull:
            cam._capture_raw(timeout_s=1.0)
        mock_pull.assert_called_once_with()


class TestPullPixelsUsesSingleImplementation:
    def _ready_camera_for_pull(self, capture_mode: str) -> SmartTouptekCamera:
        cam = SmartTouptekCamera(capture_mode=capture_mode)
        cam._cam = MagicMock()
        cam._tc = MagicMock()
        info = MagicMock(width=cam._width, height=cam._height)
        cam._tc.ToupcamFrameInfoV2.return_value = info
        return cam

    def test_snap_mode_uses_pull_image_with_row_pitch_v2(self) -> None:
        cam = self._ready_camera_for_pull("snap")
        cam._pull_pixels()
        cam._cam.PullImageWithRowPitchV2.assert_called_once()
        cam._cam.PullImageV4.assert_not_called()

    def test_stream_trigger_mode_uses_pull_image_with_row_pitch_v2(self) -> None:
        cam = self._ready_camera_for_pull("indi-stream-trigger")
        cam._pull_pixels()
        cam._cam.PullImageWithRowPitchV2.assert_called_once()
        cam._cam.PullImageV4.assert_not_called()

    def test_never_calls_toupcam_frame_info_v4(self) -> None:
        cam = self._ready_camera_for_pull("snap")
        cam._pull_pixels()
        cam._tc.ToupcamFrameInfoV4.assert_not_called()
