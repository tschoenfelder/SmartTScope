from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..domain.frame import FitsFrame


@dataclass
class SolveResult:
    success: bool
    ra: float = 0.0    # hours
    dec: float = 0.0   # degrees
    pa: float = 0.0    # position angle, degrees
    error: str | None = None


class SolverPort(ABC):
    @abstractmethod
    def solve(
        self,
        frame: FitsFrame,
        pixel_scale_hint: float,
        search_radius_deg: float | None = None,
    ) -> SolveResult: ...
