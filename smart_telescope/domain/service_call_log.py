"""ServiceCallRecord — structured per-iteration log entry (M8-015 / REQ-LOG-002)."""
from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass
class ServiceCallRecord:
    """One structured log entry for a single service invocation.

    Satisfies REQ-LOG-002 — all 11 required fields present.
    Image data is referenced by filename only (never embedded).
    """

    session_id: str
    service_name: str
    run_id: str
    iteration: int
    timestamp: str                # ISO-8601 UTC string
    input_frame_filename: str | None
    request_payload: dict
    response_payload: dict | None
    duration_ms: float
    status: str                   # "ok" | "failed" | "cancelled"
    error_if_any: str | None

    def to_dict(self) -> dict:
        return {
            "session_id":           self.session_id,
            "service_name":         self.service_name,
            "run_id":               self.run_id,
            "iteration":            self.iteration,
            "timestamp":            self.timestamp,
            "input_frame_filename": self.input_frame_filename,
            "request_payload":      self.request_payload,
            "response_payload":     self.response_payload,
            "duration_ms":          self.duration_ms,
            "status":               self.status,
            "error_if_any":         self.error_if_any,
        }

    def to_json_line(self) -> str:
        return json.dumps(self.to_dict(), default=str)
