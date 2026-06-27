"""AstapSolveRecord — structured diagnostic for one ASTAP solve attempt (M8-021 / REQ-PS-002..003)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field


@dataclass
class AstapSolveRecord:
    """Structured diagnostic record for a single ASTAP solve call.

    Logged as a JSON-line to the ``plate_solve`` section logger and to
    the adapter module logger.  All fields are set by AstapSolver.solve().
    """

    fits_path: str                     # temp FITS file fed to ASTAP
    command: list[str]                 # full command list
    exit_code: int                     # proc.returncode (-1 for timeout/launch failure)
    stdout: str                        # proc stdout (truncated to 500 chars)
    stderr: str                        # proc stderr (truncated to 500 chars)
    duration_ms: float                 # wall-clock solve time in milliseconds
    star_count: int | None             # star count passed by caller; None = not measured
    min_stars_threshold: int           # configured minimum (default 15)
    star_count_gate_passed: bool | None  # None when star_count is None
    solve_success: bool
    ra_hours: float | None = None
    dec_deg: float | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "fits_path":            self.fits_path,
            "command":              self.command,
            "exit_code":            self.exit_code,
            "stdout":               self.stdout,
            "stderr":               self.stderr,
            "duration_ms":          round(self.duration_ms, 1),
            "star_count":           self.star_count,
            "min_stars_threshold":  self.min_stars_threshold,
            "star_count_gate_passed": self.star_count_gate_passed,
            "solve_success":        self.solve_success,
            "ra_hours":             self.ra_hours,
            "dec_deg":              self.dec_deg,
            "error":                self.error,
        }

    def to_json_line(self) -> str:
        return json.dumps(self.to_dict(), default=str)
