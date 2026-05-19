"""Product-owner milestone dashboard domain.

Encodes the current backlog state as structured data so the dashboard
API and UI can render progress without parsing the todo markdown file.
Update counts here whenever a task flips done/open.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

StatusStr = Literal["green", "yellow", "red"]


@dataclass(frozen=True)
class MilestoneSummary:
    id: str
    name: str
    total: int
    done: int
    hardware_blocked: int  # open tasks that require physical hardware
    p0_open: int           # open P0 non-hardware tasks
    p1_open: int           # open P1 non-hardware tasks

    @property
    def open(self) -> int:
        return self.total - self.done

    @property
    def status(self) -> StatusStr:
        if self.p0_open > 0:
            return "red"
        if self.p1_open > 0 or (self.open - self.hardware_blocked) > 0:
            return "yellow"
        return "green"


@dataclass(frozen=True)
class RiskItem:
    id: str
    priority: str   # "P0" | "P1" | "P2"
    description: str
    milestone: str
    tags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class EvidenceGapItem:
    """A backlog item marked done but verified only with mocks, not real hardware."""
    id: str
    priority: str           # "P0" | "P1"
    description: str
    milestone: str
    mock_tested_by: str     # test file / class that covers it with mocks
    hardware_needed: str    # action needed to close the evidence gap


# ── Registry ─────────────────────────────────────────────────────────────────

MILESTONE_REGISTRY: list[MilestoneSummary] = [
    MilestoneSummary(
        id="M0", name="Project Control Restored",
        total=8, done=8, hardware_blocked=0,
        p0_open=0, p1_open=0,
    ),
    MilestoneSummary(
        id="M1", name="Hardware Safety Spine",
        total=17, done=14, hardware_blocked=3,
        p0_open=3, p1_open=0,
    ),
    MilestoneSummary(
        id="M2", name="Smart Runtime and Jobs",
        total=17, done=17, hardware_blocked=0,
        p0_open=0, p1_open=0,
    ),
    MilestoneSummary(
        id="M3", name="Smart Setup and Optical Train Truth",
        total=21, done=21, hardware_blocked=0,
        p0_open=0, p1_open=0,
    ),
    MilestoneSummary(
        id="M4", name="Intent-Driven Smart Telescope UX",
        total=23, done=22, hardware_blocked=0,
        p0_open=0, p1_open=0,
    ),
    MilestoneSummary(
        id="M5", name="Product Acceptance MVP",
        total=20, done=9, hardware_blocked=10,
        p0_open=1, p1_open=6,
    ),
    MilestoneSummary(
        id="M6", name="Field Reliability and Release Readiness",
        # R7: 001-006 (6) + M6: 001-012 (12) = 18 total
        # Done: R7-001/002/003/005/006 + M6-001..006 + M6-009 = 12
        # Open: R7-004(P0 Hw), M6-007(P1 Hw), M6-008(P2 Hw),
        #        M6-010(P1 Hw), M6-011(P1 Hw), M6-012(P1) = 6
        total=18, done=12, hardware_blocked=5,
        p0_open=1, p1_open=3,
    ),
    MilestoneSummary(
        id="COL", name="Collimation Assistant",
        total=35, done=35, hardware_blocked=0,
        p0_open=0, p1_open=0,
    ),
]

# Open P0/P1 items — top 10 risks visible to the product owner.
# Sorted: P0 first, then P1; hardware-required items last within tier.
RISK_REGISTRY: list[RiskItem] = [
    RiskItem(
        id="R7-004", priority="P0", milestone="M6",
        description="Record hardware evidence: STOP during slew, focuser move, shutdown during motion, reconnect, setup check, full workflow",
        tags=["Hardware"],
    ),
    RiskItem(
        id="R1-011", priority="P0", milestone="M1",
        description="Verify STOP during mount slew and STOP during focuser move (hardware evidence required)",
        tags=["Hardware"],
    ),
    RiskItem(
        id="M1-005", priority="P0", milestone="M1",
        description="Verify STOP during mount slew (hardware evidence)",
        tags=["Hardware"],
    ),
    RiskItem(
        id="M1-006", priority="P0", milestone="M1",
        description="Verify STOP during focuser move (hardware evidence)",
        tags=["Hardware"],
    ),
    RiskItem(
        id="M1-007", priority="P0", milestone="M1",
        description="Verify shutdown during active motion (hardware evidence)",
        tags=["Hardware"],
    ),
    RiskItem(
        id="M6-012", priority="P1", milestone="M6",
        description="Produce release notes and known issues (needed to complete release gate)",
        tags=["Process"],
    ),
    RiskItem(
        id="M6-010", priority="P1", milestone="M6",
        description="Run network reconnect simulation",
        tags=["Hardware"],
    ),
    RiskItem(
        id="M6-011", priority="P1", milestone="M6",
        description="Verify clean Pi install from scratch",
        tags=["Hardware"],
    ),
    RiskItem(
        id="M5-001", priority="P1", milestone="M5",
        description="Guided startup end-to-end",
        tags=["Hardware"],
    ),
    RiskItem(
        id="M5-011", priority="P1", milestone="M5",
        description="Stop/recover safely (hardware end-to-end evidence)",
        tags=["Hardware"],
    ),
]

# Items marked done in the backlog but verified only with mocks — no real
# hardware run has confirmed the fix yet.  Sorted P0 first, then P1.
EVIDENCE_GAPS: list[EvidenceGapItem] = [
    EvidenceGapItem(
        id="BUG-023", priority="P0", milestone="M1",
        description="Shutdown with CTRL-C must close OnStep serial connection and stop focuser motion",
        mock_tested_by="tests/unit/test_runtime.py::TestShutdown",
        hardware_needed="Run CTRL-C during active focuser move on Pi; verify serial port released and motion stopped",
    ),
    EvidenceGapItem(
        id="BUG-005", priority="P0", milestone="M1",
        description="Any component crash must not release mount/focuser control; STOP must always respond",
        mock_tested_by="tests/unit/api/test_bug005_isolation.py",
        hardware_needed="Force Python exception in camera thread on Pi; confirm STOP command halts mount within 500 ms",
    ),
    EvidenceGapItem(
        id="BUG-011", priority="P1", milestone="M1",
        description="Park command moves mount but UNPARKED flag remains too long in UI",
        mock_tested_by="tests/unit/adapters/onstep/test_onstep_mount.py",
        hardware_needed="Issue park command on real mount; verify UI label changes to PARKED within 5 s of mechanical stop",
    ),
    EvidenceGapItem(
        id="BUG-012", priority="P1", milestone="M1",
        description="After reconnect, mount shown as unparked when hardware is actually parked",
        mock_tested_by="tests/unit/adapters/onstep/test_onstep_mount.py",
        hardware_needed="Disconnect/reconnect USB on Pi; verify readiness card shows correct park state immediately",
    ),
    EvidenceGapItem(
        id="BUG-016", priority="P1", milestone="M1",
        description="Unpark returns HTTP 200 but UI label stays PARKED",
        mock_tested_by="tests/unit/adapters/onstep/test_onstep_mount.py",
        hardware_needed="Press Unpark on real mount; confirm label transitions PARKED→UNPARKED within 10 s",
    ),
    EvidenceGapItem(
        id="BUG-010", priority="P1", milestone="M3",
        description="Focuser log says not available then later available — connect ordering issue with stale serial bytes",
        mock_tested_by="tests/unit/adapters/onstep/test_onstep_focuser.py::TestConnectRetry",
        hardware_needed="Cold-start Pi with mount and focuser; confirm focuser shows available on first Connect All",
    ),
    EvidenceGapItem(
        id="BUG-013", priority="P1", milestone="M3",
        description="Setup check fails to move mount — second stale ACK byte exhausts retry and leaves serial=None",
        mock_tested_by="tests/unit/adapters/onstep/test_onstep_mount.py::TestConnectRetry",
        hardware_needed="Run Setup Check Wizard on Pi immediately after cold boot; confirm all mount steps execute",
    ),
    EvidenceGapItem(
        id="BUG-019", priority="P1", milestone="M2",
        description="Focuser nudge returns 409 conflict; rapid +20 presses mostly rejected",
        mock_tested_by="tests/unit/services/test_hardware_coordinator.py",
        hardware_needed="Press focuser +10 button 5× rapidly on real hardware; verify each press produces movement within 2 s",
    ),
]
