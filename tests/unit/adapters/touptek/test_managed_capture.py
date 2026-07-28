"""Unit tests for SmartTouptekCamera's still-image flag on capture (M10-057).

M10-056 tried forcing still=True unconditionally for "snap" mode, reasoning
that the guide camera (GPCMOS02000KPA) never fires _EVENT_STILLIMAGE for its
software-triggered captures. A real Pi log proved that hypothesis WRONG:
PullImageV4(bStill=1) failed on every single guide-camera capture with SDK
error -2147483638 (0x8000000A) -- a 100% failure rate, worse than the
original frozen-frame bug it was meant to fix. This camera is driven via
Trigger(1) (a software-triggered streaming capture), not a real Snap()-family
call, so the SDK genuinely has no still-image buffer ready when bStill=1 is
requested. M10-057 reverted to depending purely on which event actually
fired -- these tests pin that reverted (correct, hardware-confirmed) behavior
down so the disproven fix doesn't get silently reintroduced.
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
    def test_snap_mode_still_false_on_event_image(self) -> None:
        # This is guide's real-world case (GPCMOS02000KPA never fires
        # _EVENT_STILLIMAGE) -- still must stay False here, NOT be forced
        # True (that was M10-056's disproven fix; see module docstring).
        cam = _ready_camera(capture_mode="snap", fired_event=_EVENT_IMAGE)
        with patch.object(cam, "_pull_pixels", return_value="pixels") as mock_pull:
            cam._capture_raw(timeout_s=1.0)
        mock_pull.assert_called_once_with(still=False)

    def test_snap_mode_still_true_on_event_stillimage(self) -> None:
        cam = _ready_camera(capture_mode="snap", fired_event=_EVENT_STILLIMAGE)
        with patch.object(cam, "_pull_pixels", return_value="pixels") as mock_pull:
            cam._capture_raw(timeout_s=1.0)
        mock_pull.assert_called_once_with(still=True)

    def test_non_snap_mode_still_false_on_event_image(self) -> None:
        cam = _ready_camera(capture_mode="indi-stream-trigger", fired_event=_EVENT_IMAGE)
        with patch.object(cam, "_pull_pixels", return_value="pixels") as mock_pull:
            cam._capture_raw(timeout_s=1.0)
        mock_pull.assert_called_once_with(still=False)

    def test_non_snap_mode_still_true_on_stillimage_event(self) -> None:
        cam = _ready_camera(capture_mode="indi-stream-trigger", fired_event=_EVENT_STILLIMAGE)
        with patch.object(cam, "_pull_pixels", return_value="pixels") as mock_pull:
            cam._capture_raw(timeout_s=1.0)
        mock_pull.assert_called_once_with(still=True)
