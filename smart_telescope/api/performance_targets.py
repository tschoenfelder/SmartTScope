"""Performance targets API — GET /api/performance-targets."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ..domain.performance_targets import TARGETS

router = APIRouter()


@router.get("/api/performance-targets")
def get_performance_targets() -> dict[str, Any]:
    def _t(pt) -> dict[str, Any]:
        return {"value": pt.value, "unit": pt.unit, "rationale": pt.rationale}

    return {
        "session_duration_hours":    _t(TARGETS.session_duration_hours),
        "preview_latency_s":         _t(TARGETS.preview_latency_s),
        "stop_response_ms":          _t(TARGETS.stop_response_ms),
        "centering_accuracy_arcsec": _t(TARGETS.centering_accuracy_arcsec),
        "plate_solve_success_pct":   _t(TARGETS.plate_solve_success_pct),
        "pi_thermal_ceiling_c":      _t(TARGETS.pi_thermal_ceiling_c),
    }
