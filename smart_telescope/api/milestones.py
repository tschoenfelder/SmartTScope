"""Milestone dashboard API — GET /api/milestones.

Returns milestone completion statistics and the top-10 open risk items
so the product owner can see overall project health at a glance.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ..domain.milestones import EVIDENCE_GAPS, MILESTONE_REGISTRY, RISK_REGISTRY

router = APIRouter()


@router.get("/api/milestones")
def get_milestones() -> dict[str, Any]:
    milestones = [
        {
            "id": m.id,
            "name": m.name,
            "total": m.total,
            "done": m.done,
            "open": m.open,
            "hardware_blocked": m.hardware_blocked,
            "status": m.status,
        }
        for m in MILESTONE_REGISTRY
    ]
    top_risks = [
        {
            "id": r.id,
            "priority": r.priority,
            "description": r.description,
            "milestone": r.milestone,
            "tags": r.tags,
        }
        for r in RISK_REGISTRY[:10]
    ]
    return {"milestones": milestones, "top_risks": top_risks}


@router.get("/api/evidence-gaps")
def get_evidence_gaps() -> dict[str, Any]:
    """Return done items that were verified only with mocks, not real hardware."""
    items = [
        {
            "id": g.id,
            "priority": g.priority,
            "description": g.description,
            "milestone": g.milestone,
            "mock_tested_by": g.mock_tested_by,
            "hardware_needed": g.hardware_needed,
        }
        for g in EVIDENCE_GAPS
    ]
    return {"items": items, "count": len(items)}
