from __future__ import annotations
import threading, time
import numpy as np
from typing import Callable, List
from ..domain.ports import Camera, Frame

class MockCamera(Camera):
    def __init__(self, name: str = "MockCam", fps: int = 30, size: tuple[int,int,int] = (480, 640, 3)) -> None:
        self.name = name
        self._fps = fps
        self._size = size
        self._subs: List[Callable[[Frame], None]] = []
        self._run = False
        self._t: threading.Thread | None = None
        self._gain = 1.0
        self._exp = 1000

    def start(self) -> None:
        if self._run:
            return
        self._run = True
        self._t = threading.Thread(target=self._loop, daemon=True)
        self._t.start()

    def stop(self) -> None:
        self._run = False
        if self._t:
            self._t.join(timeout=1.0)

    def set_exposure(self, us: int) -> None:
        self._exp = us

    def set_gain(self, gain: float) -> None:
        self._gain = gain

    def subscribe(self, cb): self._subs.append(cb)
    def unsubscribe(self, cb):
        if cb in self._subs:
            self._subs.remove(cb)

    def _loop(self) -> None:
        period = 1.0 / max(self._fps, 1)
        t = 0.0
        while self._run:
            frame = np.zeros(self._size, np.uint8)
            # moving bar pattern for visibility
            x = int((np.sin(t) * 0.5 + 0.5) * (self._size[1]-50))
            frame[:, x:x+50, :] = 255
            for cb in list(self._subs):
                cb(frame)
            t += 0.1
            time.sleep(period)
