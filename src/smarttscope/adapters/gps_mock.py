import threading, time, math
from typing import Callable, List, Dict

class GPSMock:
    def __init__(self) -> None:
        self._subs: List[Callable[[Dict], None]] = []
        self._running = False
        self._t: threading.Thread | None = None
        self._t0 = time.time()

    def start(self) -> None:
        if self._running: return
        self._running = True
        self._t = threading.Thread(target=self._loop, daemon=True)
        self._t.start()

    def stop(self) -> None:
        self._running = False
        if self._t: self._t.join(timeout=1.0)

    def subscribe(self, cb): self._subs.append(cb)
    def unsubscribe(self, cb):
        if cb in self._subs: self._subs.remove(cb)

    def _loop(self) -> None:
        # simuliert eine kleine Kreisbewegung
        base_lat, base_lon = 50.1109, 8.6821  # Frankfurt :-)
        while self._running:
            t = time.time() - self._t0
            lat = base_lat + 0.0005 * math.sin(t/10.0)
            lon = base_lon + 0.0005 * math.cos(t/10.0)
            fix = {"lat": lat, "lon": lon, "sat": 10, "hdop": 0.9}
            for cb in list(self._subs): 
                try: cb(fix)
                except Exception: pass
            time.sleep(0.5)
