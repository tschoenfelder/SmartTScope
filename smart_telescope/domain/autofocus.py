"""Autofocus domain types — parameters and results for the V-curve sweep."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AutofocusParams:
    """Parameters for a single autofocus run."""
    range_steps:    int   # total sweep width; positions span [current - range/2, current + range/2]
    step_size:      int   # focuser steps between samples (must be > 0)
    exposure:       float # exposure per sample frame in seconds
    backlash_steps: int = 0  # pre-load overshoot to remove mechanical backlash (0 = disabled)

    def __post_init__(self) -> None:
        if self.range_steps <= 0:
            raise ValueError("range_steps must be positive")
        if self.step_size <= 0:
            raise ValueError("step_size must be positive")
        if self.exposure <= 0:
            raise ValueError("exposure must be positive")
        if self.backlash_steps < 0:
            raise ValueError("backlash_steps must be >= 0")


@dataclass
class AutofocusResult:
    """Results of a completed autofocus sweep."""
    best_position:  int
    start_position: int
    positions:      list[int]   = field(default_factory=list)
    metrics:        list[float] = field(default_factory=list)
    fitted:         bool  = False  # True when parabola fit converged
    metric_gain:    float = 0.0    # metric_at_best / metric_at_start (> 1 means improvement)

    def to_dict(self) -> dict[str, object]:
        return {
            "best_position":  self.best_position,
            "start_position": self.start_position,
            "positions":      self.positions,
            "metrics":        [round(m, 2) for m in self.metrics],
            "fitted":         self.fitted,
            "metric_gain":    round(self.metric_gain, 2),
        }
