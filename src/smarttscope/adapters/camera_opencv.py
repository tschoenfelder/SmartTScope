from __future__ import annotations
import cv2, threading, time
import numpy as np
from typing import Callable, List
from ..domain.ports import Camera, Frame
import contextlib

class OpenCVCamera(Camera):
    def __init__(self, index: int = 0, fps: int = 60, name: str = "OpenCVCam") -> None:
        self.name = name
        self._cap = cv2.VideoCapture(index)
        # set desired fps (best effort)
        self._cap.set(cv2.CAP_PROP_FPS, fps)
        self._subs: List[Callable[[Frame], None]] = []
        self._run = False
        self._t: threading.Thread | None = None

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
        self._cap.release()

    def set_exposure(self, us: int) -> None:
        # left as no-op; platform dependent to implement
        pass

    def set_gain(self, gain: float) -> None:
        # left as no-op; platform dependent to implement
        pass

    def subscribe(self, cb): self._subs.append(cb)
    def unsubscribe(self, cb):
        if cb in self._subs:
            self._subs.remove(cb)

    def _loop(self) -> None:
        while self._run:
            ok, frame = self._cap.read()
            if not ok:
                time.sleep(0.01)
                continue
            # BGR -> RGB
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            for cb in list(self._subs):
                try:
                    cb(frame)
                except RuntimeError as ex:
                    # typischer Fall: Qt-Objekt bereits gelöscht -> Abo entfernen
                    if "wrapped C/C++ object" in str(ex):
                        with contextlib.suppress(ValueError):
                            self._subs.remove(cb)
                    # andere Fehler ignorieren, Thread am Leben halten
                except Exception:
                    pass
