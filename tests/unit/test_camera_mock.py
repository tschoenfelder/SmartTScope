import time
from smarttscope.adapters.camera_mock import MockCamera

def test_mock_camera_produces_frames():
    cam = MockCamera(fps=60)
    frames = []
    cam.subscribe(lambda f: frames.append(f))
    cam.start()
    time.sleep(0.05)
    cam.stop()
    assert len(frames) > 0
    assert frames[0].ndim in (2, 3)
