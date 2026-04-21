from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class SolveResult:
    success: bool
    ra: float = 0.0    # hours
    dec: float = 0.0   # degrees
    pa: float = 0.0    # position angle, degrees
    error: str | None = None


class SolverPort(ABC):
    @abstractmethod
    def solve(self, frame_data: bytes, pixel_scale_hint: float) -> SolveResult: ...
