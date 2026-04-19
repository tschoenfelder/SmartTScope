from typing import List, Optional

from ...ports.solver import SolverPort, SolveResult

# M42 coordinates — default happy-path solve result
_M42_SOLVE = SolveResult(success=True, ra=5.5881, dec=-5.391, pa=0.0)


class MockSolver(SolverPort):
    def __init__(
        self,
        results: Optional[List[SolveResult]] = None,
        always_fail: bool = False,
    ) -> None:
        if always_fail:
            self._results = [SolveResult(success=False, error="Mock: solve failed")]
        else:
            self._results = results if results is not None else [_M42_SOLVE]
        self._call_index = 0

    def solve(self, frame_data: bytes, pixel_scale_hint: float) -> SolveResult:
        result = self._results[min(self._call_index, len(self._results) - 1)]
        self._call_index += 1
        return result
