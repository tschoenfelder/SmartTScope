from __future__ import annotations
from typing import Callable, List, Tuple
import threading, time, contextlib
import numpy as np
from picamera2 import Picamera2
from ..domain.ports import Camera, Frame

class Picamera2Camera(Camera):
    def __init__(self, index: int = 0, size: Tuple[int,int]=(1280,720), name: str="PiCam") -> None:
        self.name = name
        self._pi = Picamera2(camera_num=index)  # <— WICHTIG: camera_num
        self._pi.configure(self._pi.create_preview_configuration(main={"size": size, "format": "RGB888"}))
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
        with contextlib.suppress(Exception):
            self._pi.stop()
        with contextlib.suppress(Exception):
            self._pi.close()

    def set_exposure(self, us: int) -> None:
        self._pi.set_controls({"ExposureTime": int(us)})

    def set_gain(self, gain: float) -> None:
        self._pi.set_controls({"AnalogueGain": float(gain)})

    def subscribe(self, cb): self._subs.append(cb)
    def unsubscribe(self, cb):
        with contextlib.suppress(ValueError):
            self._subs.remove(cb)

    def _loop(self) -> None:
        while self._run:
            try:
                arr = self._pi.capture_array("main")
            except Exception:
                break
            for cb in list(self._subs):
                try:
                    cb(arr)
                except RuntimeError as ex:
                    if "wrapped C/C++ object" in str(ex):
                        with contextlib.suppress(ValueError):
                            self._subs.remove(cb)
                except Exception:
                    pass
            time.sleep(0)
