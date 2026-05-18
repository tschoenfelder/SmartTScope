"""Operational performance targets for SmartTScope field use.

These numbers define the acceptance bar for M6 field reliability tests
and feed the release go/no-go checklist (docs/release-checklist.md).
Update values here when the product owner revises a target.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PerformanceTarget:
    value: float
    unit: str
    rationale: str


@dataclass(frozen=True)
class PerformanceTargets:
    # M6-001 — unattended session duration
    session_duration_hours: PerformanceTarget

    # M6-002 — preview frame latency (camera → browser display)
    preview_latency_s: PerformanceTarget

    # M6-003 — STOP command response (command issued → hardware halted)
    stop_response_ms: PerformanceTarget

    # M6-004 — plate-solve / recenter accuracy
    centering_accuracy_arcsec: PerformanceTarget

    # M6-005 — plate solve success rate under normal conditions
    plate_solve_success_pct: PerformanceTarget

    # M6-006 — Raspberry Pi 5 thermal ceiling under sustained load
    pi_thermal_ceiling_c: PerformanceTarget


TARGETS = PerformanceTargets(
    session_duration_hours=PerformanceTarget(
        value=6.0,
        unit="hours",
        rationale="Covers a typical summer/winter night without intervention",
    ),
    preview_latency_s=PerformanceTarget(
        value=2.0,
        unit="seconds",
        rationale="User sees live sky within 2 s of each exposure completing",
    ),
    stop_response_ms=PerformanceTarget(
        value=500.0,
        unit="ms",
        rationale="Mount/focuser motion halts within 500 ms of STOP command; "
                  "matches POD-002 cancel-latency decision",
    ),
    centering_accuracy_arcsec=PerformanceTarget(
        value=30.0,
        unit="arcsec",
        rationale="Target within 30 arcsec RMS after one plate-solve/recenter cycle "
                  "at f/10 (C8 main camera, 0.63 arcsec/px pixel scale)",
    ),
    plate_solve_success_pct=PerformanceTarget(
        value=90.0,
        unit="%",
        rationale="≥ 90% first-attempt solve rate under clear dark-sky conditions "
                  "with ASTAP and full catalog installed",
    ),
    pi_thermal_ceiling_c=PerformanceTarget(
        value=75.0,
        unit="°C",
        rationale="Raspberry Pi 5 throttles at 80°C; 75°C gives 5°C headroom "
                  "during sustained imaging and solver load",
    ),
)
