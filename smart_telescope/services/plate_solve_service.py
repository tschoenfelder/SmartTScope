"""Stateful plate-solve service wrapping AstapSolver (M7-006 / PS-001..PS-004).

Responsibilities:
- Enforces PS-001: auto-gain with reason PLATE_SOLVE must complete before solving.
- Tracks retry count, last result, and auto-gain completion status.
- Delegates the actual solve to the existing AstapSolver.
- Does NOT sync or move the mount (PS-004).
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..adapters.astap.solver import AstapSolver
    from ..domain.frame import FitsFrame

_log = logging.getLogger(__name__)


class PlateSolveState(Enum):
    IDLE      = auto()
    SOLVING   = auto()
    SUCCESS   = auto()
    FAILED    = auto()


class PlateSolveError(Exception):
    """Raised when a precondition blocks the solve (e.g. auto-gain not done)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass
class SolveOutput:
    """PS-003 output from one plate-solve attempt."""
    solved: bool
    ra: float | None = None              # hours
    dec: float | None = None             # degrees
    number_of_stars_found: int | None = None
    median_fwhm_px: float | None = None
    diagnostics: str | None = None
    # PS-003 solver_return_values
    calculated_focal_length_mm: float | None = None
    calculated_pixel_scale_arcsec_per_px: float | None = None
    field_rotation_deg: float | None = None
    solver_runtime_s: float | None = None
    solver_name: str = "ASTAP"
    solver_status: str | None = None


class PlateSolveService:
    """Stateful plate-solving service wrapping AstapSolver.

    Thread-safe: all state is protected by a single lock.

    Typical flow:
        svc.mark_autogain_complete()          # after auto-gain finishes
        result = svc.solve(frame, scale_hint) # blocks; sets SUCCESS or FAILED
    """

    def __init__(self, solver: "AstapSolver", max_retries: int = 5) -> None:
        self._solver = solver
        self._max_retries = max_retries
        self._lock = threading.Lock()
        self._state = PlateSolveState.IDLE
        self._autogain_done: bool = False
        self._retry_count: int = 0
        self._last_result: SolveOutput | None = None

    # ── public API ────────────────────────────────────────────────────────────

    @property
    def state(self) -> PlateSolveState:
        with self._lock:
            return self._state

    @property
    def retry_count(self) -> int:
        with self._lock:
            return self._retry_count

    @property
    def last_result(self) -> SolveOutput | None:
        with self._lock:
            return self._last_result

    def mark_autogain_complete(self) -> None:
        """Signal that auto-gain with reason PLATE_SOLVE has finished (PS-001)."""
        with self._lock:
            self._autogain_done = True
        _log.info("PlateSolveService: auto-gain complete — solving is now permitted")

    def reset(self) -> None:
        """Reset service state for a new plate-solving session."""
        with self._lock:
            self._state = PlateSolveState.IDLE
            self._autogain_done = False
            self._retry_count = 0
            self._last_result = None

    def solve(
        self,
        frame: "FitsFrame",
        pixel_scale_hint: float,
        search_radius_deg: float | None = None,
    ) -> SolveOutput:
        """Run a plate-solve attempt.

        Raises:
            PlateSolveError: if auto-gain has not been completed (PS-001).
        """
        with self._lock:
            if not self._autogain_done:
                raise PlateSolveError(
                    "Plate solving requires auto-gain with reason PLATE_SOLVE to complete first (PS-001). "
                    "Call mark_autogain_complete() after auto-gain finishes."
                )
            if self._retry_count >= self._max_retries:
                raise PlateSolveError(
                    f"Plate-solve retry limit reached ({self._max_retries}). "
                    "Call reset() to start a new session."
                )
            self._state = PlateSolveState.SOLVING
            self._retry_count += 1
            retry = self._retry_count

        _log.info(
            "PlateSolveService: starting solve attempt %d (scale=%.4f arcsec/px)",
            retry, pixel_scale_hint,
        )
        t0 = time.monotonic()
        try:
            result = self._solver.solve(
                frame,
                pixel_scale_hint=pixel_scale_hint,
                search_radius_deg=search_radius_deg,
            )
        except Exception as exc:
            elapsed = time.monotonic() - t0
            output = SolveOutput(
                solved=False,
                diagnostics=f"Solver exception: {exc}",
                solver_runtime_s=elapsed,
                solver_status="EXCEPTION",
            )
            with self._lock:
                self._state = PlateSolveState.FAILED
                self._last_result = output
            return output

        elapsed = time.monotonic() - t0
        if result.success:
            output = SolveOutput(
                solved=True,
                ra=result.ra,
                dec=result.dec,
                field_rotation_deg=result.pa,
                solver_runtime_s=elapsed,
                solver_name="ASTAP",
                solver_status="PLATESOLVED",
            )
            with self._lock:
                self._state = PlateSolveState.SUCCESS
                self._last_result = output
        else:
            output = SolveOutput(
                solved=False,
                diagnostics=result.error,
                solver_runtime_s=elapsed,
                solver_name="ASTAP",
                solver_status="PLATESOLVED_FALSE",
            )
            with self._lock:
                self._state = PlateSolveState.FAILED
                self._last_result = output

        _log.info(
            "PlateSolveService: solve attempt %d finished in %.1fs — solved=%s",
            retry, elapsed, output.solved,
        )
        return output
