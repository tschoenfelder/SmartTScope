"""Domain types for measure-only fast guiding."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class GuideSourceHealth(str, Enum):
    HEALTHY = "healthy"
    TRANSIENT_BAD = "transient_bad"
    HARD_FAILED = "hard_failed"


@dataclass(frozen=True)
class GuideFrame:
    role: str
    sequence: int
    captured_at_monotonic: float
    received_at_monotonic: float
    exposure_s: float
    shape: tuple[int, int]
    dtype: str
    dropped_before: int = 0

    @property
    def frame_age_s(self) -> float:
        return max(0.0, self.received_at_monotonic - self.captured_at_monotonic)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["shape"] = list(self.shape)
        data["frame_age_s"] = round(self.frame_age_s, 3)
        return data


@dataclass(frozen=True)
class GuideMeasurement:
    role: str
    sequence: int
    accepted: bool
    centroid_x: float | None = None
    centroid_y: float | None = None
    target_x: float | None = None
    target_y: float | None = None
    error_x: float | None = None
    error_y: float | None = None
    confidence: float = 0.0
    peak: float = 0.0
    background: float = 0.0
    noise: float = 0.0
    saturated: bool = False
    fwhm_px: float | None = None
    rejected_reason: str | None = None
    frame_age_s: float = 0.0
    measured_at_monotonic: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WouldGuidePulse:
    axis: str
    direction: str
    duration_ms: int
    reason: str
    clipped: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GuideSourceState:
    role: str
    running: bool
    health: GuideSourceHealth
    latest_sequence: int = 0
    latest_frame_age_s: float | None = None
    bad_frame_count: int = 0
    hard_failure: str | None = None
    measurement: GuideMeasurement | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["health"] = self.health.value
        if self.measurement is not None:
            data["measurement"] = self.measurement.to_dict()
        return data
