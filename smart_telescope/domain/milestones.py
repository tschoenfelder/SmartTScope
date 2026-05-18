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
        # Done: R7-001/002/003/005 + M6-001..006 + M6-009 = 11
        # Open: R7-004(P0 Hw), R7-006(P2), M6-007(P1 Hw), M6-008(P2 Hw),
        #        M6-010(P1 Hw), M6-011(P1 Hw), M6-012(P1) = 7
        total=18, done=11, hardware_blocked=5,
        p0_open=1, p1_open=4,
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
        id="M6-003", priority="P1", milestone="M6",
        description="Define stop-response time target (process — needed for release gate)",
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
