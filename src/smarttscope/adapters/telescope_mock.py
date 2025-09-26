class TelescopeMock:
    def __init__(self) -> None:
        self.connected = False
        self.ra = 0.0
        self.dec = 0.0

    def connect(self) -> None: self.connected = True
    def disconnect(self) -> None: self.connected = False

    def goto(self, ra_hours: float, dec_deg: float) -> None:
        if not self.connected: raise RuntimeError("telescope not connected")
        self.ra, self.dec = ra_hours, dec_deg

    def nudge(self, axis: str, rate: float, seconds: float) -> None:
        if not self.connected: raise RuntimeError("telescope not connected")
        delta = rate * seconds / 3600.0  # grob
        if axis.lower().startswith("ra"): self.ra += delta
        else: self.dec += delta
