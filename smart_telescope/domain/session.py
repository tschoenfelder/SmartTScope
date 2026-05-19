from dataclasses import dataclass, field
from datetime import datetime

from .frame_quality import FrameQualityEntry
from .states import SessionState


@dataclass
class StageTimestamp:
    stage: str
    started_at: datetime
    completed_at: datetime | None = None


@dataclass
class SessionLog:
    session_id: str
    target_name: str
    target_ra: float
    target_dec: float
    optical_config: str
    started_at: datetime
    state: SessionState = SessionState.IDLE
    stage_timestamps: list[StageTimestamp] = field(default_factory=list)
    frames_integrated: int = 0
    frames_rejected: int = 0
    plate_solve_attempts: int = 0
    centering_offset_arcmin: float = 0.0
    centering_iterations: int = 0
    centering_state: str | None = None  # "CENTERED" or "CENTERING_DEGRADED"
    autofocus_best_position: int | None = None
    autofocus_metric_gain: float | None = None
    refocus_count: int = 0  # number of mid-stack refocuses performed
    frame_quality_log: list[FrameQualityEntry] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    failure_stage: str | None = None
    failure_reason: str | None = None
    saved_image_path: str | None = None
    saved_log_path: str | None = None
    completed_at: datetime | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "target": {
                "name": self.target_name,
                "ra": self.target_ra,
                "dec": self.target_dec,
            },
            "optical_config": self.optical_config,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "final_state": self.state.name,
            "stage_timestamps": [
                {
                    "stage": ts.stage,
                    "started_at": ts.started_at.isoformat(),
                    "completed_at": ts.completed_at.isoformat() if ts.completed_at else None,
                }
                for ts in self.stage_timestamps
            ],
            "frames_integrated": self.frames_integrated,
            "frames_rejected": self.frames_rejected,
            "plate_solve_attempts": self.plate_solve_attempts,
            "centering_offset_arcmin": self.centering_offset_arcmin,
            "centering_iterations": self.centering_iterations,
            "centering_state": self.centering_state,
            "autofocus": {
                "best_position": self.autofocus_best_position,
                "metric_gain": self.autofocus_metric_gain,
                "refocus_count": self.refocus_count,
            },
            "frame_quality_log": [
                {
                    "frame": e.frame_number,
                    "snr": round(e.snr, 2),
                    "baseline_snr": round(e.baseline_snr, 2) if e.baseline_snr is not None else None,
                    "accepted": e.accepted,
                    "reason": e.reason,
                }
                for e in self.frame_quality_log
            ],
            "warnings": self.warnings,
            "failure_stage": self.failure_stage,
            "failure_reason": self.failure_reason,
            "saved_artifacts": {
                "image": self.saved_image_path,
                "log": self.saved_log_path,
            },
        }
