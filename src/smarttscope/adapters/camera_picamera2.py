from __future__ import annotations
from typing import Callable, List, Tuple
import threading, time, contextlib
from collections import deque
import numpy as np
from picamera2 import Picamera2
from ..domain.ports import Camera, Frame

class Picamera2Camera(Camera):
    def __init__(self, index: int = 0, size: Tuple[int,int]=(1280,720), name: str="PiCam") -> None:
        self.name = name
        self._pi = Picamera2(camera_num=index)  # <— WICHTIG: camera_num

        cfg = self._pi.create_video_configuration(
            main={"size": size, "format": "RGB888"},
            lores={"size": (640, 360), "format": "RGB888"},
            buffer_count=3,          # kleiner halten, weniger Stau
        )
        self._pi.configure(cfg)
##        self._pi.configure(self._pi.create_preview_configuration(main={"size": size, "format": "RGB888"}))
        self._stream = os.getenv("SMARTTSCOPE_PREVIEW_STREAM", "lores")
        if self._stream not in ("lores","main"): self._stream = "lores"

        # adaptive Ziele
        self._min_fps, self._max_fps = 5, 30       # Korridor
        self._target_fps = int(os.getenv("SMARTTSCOPE_MAX_FPS", "0") or 0) or 15
        self._frame_interval_us = int(1_000_000 / self._target_fps)
        self._ewma_cb_ms = 0.0                     # gleitender Mittelwert der Callback-Zeit
        self._alpha = 0.2                          # Glättung
        # initiale Limits setzen
        self._apply_frame_duration(self._frame_interval_us)

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

    def _apply_frame_duration(self, usec: int):
        usec = max( int(1_000_000/self._max_fps), min( int(1_000_000/self._min_fps), usec) )
        with contextlib.suppress(Exception):
            self._pi.set_controls({"FrameDurationLimits": (usec, usec)})
        self._frame_interval_us = usec

    def subscribe(self, cb): self._subs.append(cb)
    def unsubscribe(self, cb):
        with contextlib.suppress(ValueError):
            self._subs.remove(cb)

    def _loop(self) -> None:
        last_adjust = 0.0
        while self._run:
            try:
##                arr = self._pi.capture_array("main")
                t0 = time.perf_counter()
                arr = self._pi.capture_array(self._stream)
            except Exception:
                break

             # Messung: wie lange brauchen Abonnenten?
            cb_start = time.perf_counter()
            for cb in list(self._subs):
                try:
                    cb(arr)
                except RuntimeError as ex:
                    if "wrapped C/C++ object" in str(ex):
                        with contextlib.suppress(ValueError):
                            self._subs.remove(cb)
                except Exception:
                    pass

            cb_ms = (time.perf_counter() - cb_start) * 1000.0
            # EWMA aktualisieren
            self._ewma_cb_ms = (1.0 - self._alpha)*self._ewma_cb_ms + self._alpha*cb_ms
            
            # alle 0.5 s anpassen, wenn nötig
            now = time.perf_counter()
            if now - last_adjust > 0.5:
                last_adjust = now
                # gewünschter headroom: callbacks ~ 40% des Frameintervalls
                interval_ms = self._frame_interval_us / 1000.0
                util = self._ewma_cb_ms / max(1e-3, interval_ms)
                if util > 0.7:
                    # zu viel Last -> fps runter (multiplikativ)
                    new_fps = max(self._min_fps, int((1000.0 / max(15.0, self._ewma_cb_ms)) * 0.8))
                    new_usec = int(1_000_000 / new_fps)
                    if abs(new_usec - self._frame_interval_us) > 5_000:
                        self._apply_frame_duration(new_usec)
                elif util < 0.3 and self._target_fps < self._max_fps:
                    # Luft nach oben -> langsam erhöhen (additiv)
                    new_fps = min(self._max_fps, int(1000.0 / max(1.0, interval_ms) + 1))
                    new_usec = int(1_000_000 / new_fps)
                    if abs(new_usec - self._frame_interval_us) > 5_000:
                        self._apply_frame_duration(new_usec)

            # optional: wenn keinerlei Subs -> klein schlafen
            if not self._subs:
                time.sleep(0.01)

            time.sleep(0)
