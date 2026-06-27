from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..domain.frame import FitsFrame

if TYPE_CHECKING:
    from ..domain.astap_diagnostic import AstapSolveRecord


@dataclass
class SolveResult:
    success: bool
    ra: float = 0.0    # hours
    dec: float = 0.0   # degrees
    pa: float = 0.0    # position angle, degrees
    error: str | None = None
    diagnostics: "AstapSolveRecord | None" = field(default=None, compare=False, repr=False)


class SolverPort(ABC):
    @abstractmethod
    def solve(
        self,
        frame: FitsFrame,
        pixel_scale_hint: float,
        search_radius_deg: float | None = None,
    ) -> SolveResult: ...
