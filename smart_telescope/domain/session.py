from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List

from .states import SessionState


@dataclass
class StageTimestamp:
    stage: str
    started_at: datetime
    completed_at: Optional[datetime] = None


@dataclass
class SessionLog:
    session_id: str
    target_name: str
    target_ra: float
    target_dec: float
    optical_config: str
    started_at: datetime
    state: SessionState = SessionState.IDLE
    stage_timestamps: List[StageTimestamp] = field(default_factory=list)
    frames_integrated: int = 0
    frames_rejected: int = 0
    plate_solve_attempts: int = 0
    centering_offset_arcmin: float = 0.0
    centering_iterations: int = 0
    warnings: List[str] = field(default_factory=list)
    failure_stage: Optional[str] = None
    failure_reason: Optional[str] = None
    saved_image_path: Optional[str] = None
    saved_log_path: Optional[str] = None
    completed_at: Optional[datetime] = None

    def to_dict(self) -> dict:
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
            "warnings": self.warnings,
            "failure_stage": self.failure_stage,
            "failure_reason": self.failure_reason,
            "saved_artifacts": {
                "image": self.saved_image_path,
                "log": self.saved_log_path,
            },
        }
