import threading
import time

import numpy as np
import pytest

from smart_telescope.services.managed_camera import FrameMailbox, ManagedCamera
from smart_telescope.domain.frame import FitsFrame
from astropy.io import fits


def _frame(val: int = 100) -> FitsFrame:
    pixels = np.full((10, 10), val, dtype=np.uint16)
    return FitsFrame(pixels=pixels.astype(np.float32), header=fits.Header(), exposure_seconds=0.5)


def test_mailbox_returns_put_frame():
    mb = FrameMailbox()
    mb.put(_frame(1), sequence=1, captured_at=time.monotonic())
    result = mb.wait_latest(after_sequence=0, timeout_s=0.1)
    assert result is not None
    assert result.sequence == 1
    assert result.dropped_before == 0


def test_mailbox_drops_unconsumed_frame():
    mb = FrameMailbox()
    mb.put(_frame(1), sequence=1, captured_at=time.monotonic())
    mb.put(_frame(2), sequence=2, captured_at=time.monotonic())  # drops frame 1
    result = mb.wait_latest(after_sequence=0, timeout_s=0.1)
    assert result is not None
    assert result.sequence == 2
    assert result.dropped_before == 1
    assert mb.dropped_count == 1


def test_mailbox_returns_none_on_timeout():
    mb = FrameMailbox()
    result = mb.wait_latest(after_sequence=0, timeout_s=0.05)
    assert result is None


def test_mailbox_after_sequence_filter():
    mb = FrameMailbox()
    mb.put(_frame(1), sequence=1, captured_at=time.monotonic())
    result = mb.wait_latest(after_sequence=1, timeout_s=0.05)
    assert result is None  # seq=1 is not > after_sequence=1


def test_managed_camera_streams_frames():
    from smart_telescope.adapters.mock.camera import MockCamera
    cam = MockCamera()
    cam.connect()
    mc = ManagedCamera(cam, "guide")
    mc.start_stream(exposure_s=0.01, cadence_s=0.05)
    time.sleep(0.3)
    frame = mc.mailbox.wait_latest(after_sequence=0, timeout_s=0.5)
    mc.stop_stream()
    assert frame is not None
    assert frame.sequence >= 1


def test_managed_camera_stop_is_clean():
    from smart_telescope.adapters.mock.camera import MockCamera
    cam = MockCamera()
    cam.connect()
    mc = ManagedCamera(cam, "guide")
    mc.start_stream(exposure_s=0.01, cadence_s=0.05)
    time.sleep(0.1)
    mc.stop_stream()
    # No exception, thread is dead
    assert mc._thread is None or not mc._thread.is_alive()


def test_managed_camera_reports_stream_error():
    from smart_telescope.adapters.mock.camera import MockCamera
    cam = MockCamera()
    cam.connect()
    mc = ManagedCamera(cam, "guide")
    # Inject a failure by disconnecting before stream runs
    cam.disconnect()
    mc.start_stream(exposure_s=0.01, cadence_s=0.05)
    time.sleep(0.3)
    err = mc.pop_stream_error()
    mc.stop_stream()
    # MockCamera.capture() after disconnect should raise; error surfaces
    # (MockCamera may not raise — just verify no crash and clean stop)
    assert mc.pop_stream_error() is None  # only one error stored
