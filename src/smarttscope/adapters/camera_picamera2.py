from __future__ import annotations
import threading, time
from typing import Callable, List, Tuple
import numpy as np
from ..domain.ports import Camera, Frame

class Picamera2Camera(Camera):
    def __init__(self, index: int = 0, size: Tuple[int,int] = (1280, 720), name: str = "PiCam") -> None:
        # Lazy import to keep non-Pi environments working
        from picamera2 import Picamera2
        self.name = name
        self._pi = Picamera2(index)
        self._pi.configure(self._pi.create_preview_configuration(main={"size": size, "format":"RGB888"}))
        self._subs: List[Callable[[Frame], None]] = []
        self._run = False
        self._t: threading.Thread | None = None

    def start(self) -> None:
        if self._run:
            return
        self._pi.start()
        self._run = True
        self._t = threading.Thread(target=self._loop, daemon=True)
        self._t.start()

    def stop(self) -> None:
        self._run = False
        if self._t:
            self._t.join(timeout=1.0)
        self._pi.stop()

    def set_exposure(self, us: int) -> None:
        self._pi.set_controls({"ExposureTime": int(us)})

    def set_gain(self, gain: float) -> None:
        self._pi.set_controls({"AnalogueGain": float(gain)})

    def subscribe(self, cb): self._subs.append(cb)
    def unsubscribe(self, cb):
        if cb in self._subs:
            self._subs.remove(cb)

    def _loop(self) -> None:
        # capture arrays while running; Picamera2 converts to numpy
        while self._run:
            arr = self._pi.capture_array("main")
            for cb in list(self._subs):
                cb(arr)
            # let other threads breathe
            time.sleep(0.0)
