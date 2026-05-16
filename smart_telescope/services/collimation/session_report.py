"""Session report — Collimation Phase 12, COL-122.

Produces a structured :class:`CollimationSessionReport` that captures the
complete outcome of a collimation session.  The :class:`SessionReportBuilder`
is the single point of write access; call ``build()`` to obtain an immutable
snapshot.

Overall status values
---------------------
"complete"        : final validation passed with good error ratio.
"acceptable"      : marginal but within fallback ratio.
"seeing_limited"  : jitter prevented a definitive conclusion.
"failed"          : error too large, or session ended with a failed state.
"in_progress"     : ``build()`` was called before a final result was recorded.
"cancelled"       : session was cancelled before completion.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from .maskless_validator import ValidationReport


@dataclass(frozen=True)
class CollimationSessionReport:
    """Immutable snapshot of a completed collimation session.

    Fields
    ------
    telescope_profile   : optical-train profile name.
    camera_id           : camera device identifier.
    started_at          : UNIX timestamp when the session started (or None).
    finished_at         : UNIX timestamp when the session finished (or None).
    selected_star       : name of the guide star used (or None if unknown).
    rough_started_at    : timestamp for rough-collimation phase start.
    rough_finished_at   : timestamp for rough-collimation phase end.
    fine_started_at     : timestamp for fine-collimation phase start.
    fine_finished_at    : timestamp for fine-collimation phase end.
    initial_focus_fwhm_px : FWHM at session start (px).
    final_focus_fwhm_px : FWHM at session end (px).
    final_donut_error_px: residual collimation error at session end (px).
    final_donut_status  : status string from :class:`ValidationReport`.
    seeing_jitter_px    : recorded seeing jitter (px).
    overall_status      : session outcome (see module docstring).
    warnings            : aggregated advisory messages.
    """
    telescope_profile: str
    camera_id: str
    started_at: float | None
    finished_at: float | None
    selected_star: str | None
    rough_started_at: float | None
    rough_finished_at: float | None
    fine_started_at: float | None
    fine_finished_at: float | None
    initial_focus_fwhm_px: float | None
    final_focus_fwhm_px: float | None
    final_donut_error_px: float | None
    final_donut_status: str | None
    seeing_jitter_px: float | None
    overall_status: str
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return a plain JSON-serialisable dictionary."""
        return {
            "telescope_profile":    self.telescope_profile,
            "camera_id":            self.camera_id,
            "started_at":           self.started_at,
            "finished_at":          self.finished_at,
            "selected_star":        self.selected_star,
            "rough_started_at":     self.rough_started_at,
            "rough_finished_at":    self.rough_finished_at,
            "fine_started_at":      self.fine_started_at,
            "fine_finished_at":     self.fine_finished_at,
            "initial_focus_fwhm_px": self.initial_focus_fwhm_px,
            "final_focus_fwhm_px":  self.final_focus_fwhm_px,
            "final_donut_error_px": self.final_donut_error_px,
            "final_donut_status":   self.final_donut_status,
            "seeing_jitter_px":     self.seeing_jitter_px,
            "overall_status":       self.overall_status,
            "warnings":             list(self.warnings),
        }

    def to_text(self) -> str:
        """Return a human-readable plain-text summary."""
        lines = [
            "=== Collimation Session Report ===",
            f"  Profile  : {self.telescope_profile}",
            f"  Camera   : {self.camera_id}",
        ]
        if self.selected_star:
            lines.append(f"  Star     : {self.selected_star}")
        lines.append(f"  Status   : {self.overall_status.upper()}")
        lines.append("")
        lines.append("  Focus:")
        if self.initial_focus_fwhm_px is not None:
            lines.append(f"    Initial FWHM : {self.initial_focus_fwhm_px:.2f} px")
        if self.final_focus_fwhm_px is not None:
            lines.append(f"    Final FWHM   : {self.final_focus_fwhm_px:.2f} px")
        if self.seeing_jitter_px is not None:
            lines.append(f"    Seeing jitter: {self.seeing_jitter_px:.2f} px")
        lines.append("  Collimation:")
        if self.final_donut_error_px is not None:
            lines.append(f"    Donut error  : {self.final_donut_error_px:.2f} px")
        if self.final_donut_status:
            lines.append(f"    Verdict      : {self.final_donut_status}")
        if self.warnings:
            lines.append("  Warnings:")
            for w in self.warnings:
                lines.append(f"    - {w}")
        lines.append("===================================")
        return "\n".join(lines)


class SessionReportBuilder:
    """Accumulates session data and builds a :class:`CollimationSessionReport`.

    Usage::

        builder = SessionReportBuilder()
        builder.set_optical_train("c8-celestron")
        builder.set_camera("touptek-iag130m")
        builder.record_rough_start()
        ...
        builder.record_final_result(validation_report)
        report = builder.build()
    """

    def __init__(self) -> None:
        self._telescope_profile: str = ""
        self._camera_id: str = ""
        self._selected_star: str | None = None
        self._started_at: float | None = None
        self._finished_at: float | None = None
        self._rough_started_at: float | None = None
        self._rough_finished_at: float | None = None
        self._fine_started_at: float | None = None
        self._fine_finished_at: float | None = None
        self._initial_focus_fwhm: float | None = None
        self._final_focus_fwhm: float | None = None
        self._final_validation: ValidationReport | None = None
        self._seeing_jitter_px: float | None = None
        self._cancelled: bool = False
        self._warnings: list[str] = []

    # ── Setters ───────────────────────────────────────────────────────────────

    def set_optical_train(self, telescope_profile: str) -> None:
        self._telescope_profile = telescope_profile

    def set_camera(self, camera_id: str) -> None:
        self._camera_id = camera_id

    def set_selected_star(self, star_name: str) -> None:
        self._selected_star = star_name

    def record_rough_start(self, timestamp: float | None = None) -> None:
        ts = timestamp if timestamp is not None else time.time()
        if self._started_at is None:
            self._started_at = ts
        self._rough_started_at = ts

    def record_rough_end(self, timestamp: float | None = None) -> None:
        self._rough_finished_at = timestamp if timestamp is not None else time.time()

    def record_fine_start(self, timestamp: float | None = None) -> None:
        self._fine_started_at = timestamp if timestamp is not None else time.time()

    def record_fine_end(self, timestamp: float | None = None) -> None:
        self._fine_finished_at = timestamp if timestamp is not None else time.time()

    def record_focus_status(
        self,
        initial_fwhm: float | None,
        final_fwhm: float | None,
    ) -> None:
        self._initial_focus_fwhm = initial_fwhm
        self._final_focus_fwhm   = final_fwhm

    def record_seeing(self, jitter_px: float) -> None:
        self._seeing_jitter_px = jitter_px

    def record_final_result(self, validation: ValidationReport) -> None:
        self._final_validation = validation
        self._finished_at = time.time()
        self._warnings.extend(validation.warnings)

    def mark_cancelled(self) -> None:
        self._cancelled = True
        self._finished_at = time.time()

    # ── Build ─────────────────────────────────────────────────────────────────

    def build(self) -> CollimationSessionReport:
        """Produce an immutable :class:`CollimationSessionReport` snapshot."""
        overall_status = self._derive_status()
        donut_error: float | None = None
        donut_status: str | None  = None
        if self._final_validation is not None:
            donut_error  = self._final_validation.donut_error_px
            donut_status = self._final_validation.status

        return CollimationSessionReport(
            telescope_profile=self._telescope_profile,
            camera_id=self._camera_id,
            started_at=self._started_at,
            finished_at=self._finished_at,
            selected_star=self._selected_star,
            rough_started_at=self._rough_started_at,
            rough_finished_at=self._rough_finished_at,
            fine_started_at=self._fine_started_at,
            fine_finished_at=self._fine_finished_at,
            initial_focus_fwhm_px=self._initial_focus_fwhm,
            final_focus_fwhm_px=self._final_focus_fwhm,
            final_donut_error_px=donut_error,
            final_donut_status=donut_status,
            seeing_jitter_px=self._seeing_jitter_px,
            overall_status=overall_status,
            warnings=list(self._warnings),
        )

    # ── Private ───────────────────────────────────────────────────────────────

    def _derive_status(self) -> str:
        if self._cancelled:
            return "cancelled"
        if self._final_validation is None:
            return "in_progress"
        status_map = {
            "complete":               "complete",
            "acceptable_with_warning": "acceptable",
            "seeing_limited":         "seeing_limited",
            "failed":                 "failed",
        }
        return status_map.get(self._final_validation.status, "failed")
