"""POST /api/histogram/analyze — one-shot histogram from a live camera frame."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..domain.histogram import HistogramStats, analyze, histogram_bins
from . import deps

router = APIRouter(prefix="/api/histogram")


class HistogramResponse(BaseModel):
    # HistogramStats fields
    p50: float
    p95: float
    p99: float
    p99_5: float
    p99_9: float
    mean_frac: float
    saturation_pct: float
    zero_clipped_pct: float
    black_level: float
    effective_bit_depth: int
    adc_max: float
    # Bin data for the UI histogram widget
    bin_counts: list[int]
    bin_edges: list[float]   # length = len(bin_counts) + 1


@router.post("/analyze", response_model=HistogramResponse)
async def analyze_histogram(
    camera_index: int = Query(default=0, ge=0, le=7),
    exposure: float = Query(default=2.0, gt=0.0, le=60.0),
    gain: int = Query(default=100, ge=0),
    bit_depth: int = Query(default=12, ge=8, le=16),
    n_bins: int = Query(default=512, ge=64, le=4096),
) -> HistogramResponse:
    """Capture one frame and return its histogram statistics and bin data."""
    try:
        camera = deps.get_preview_camera(camera_index)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    camera.set_gain(gain)
    try:
        frame = await asyncio.to_thread(camera.capture, exposure)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Camera capture failed: {exc}") from exc

    stats: HistogramStats = analyze(frame.pixels, bit_depth=bit_depth)
    counts, edges = histogram_bins(frame.pixels, bit_depth=bit_depth, n_bins=n_bins)

    return HistogramResponse(
        p50=stats.p50,
        p95=stats.p95,
        p99=stats.p99,
        p99_5=stats.p99_5,
        p99_9=stats.p99_9,
        mean_frac=stats.mean_frac,
        saturation_pct=stats.saturation_pct,
        zero_clipped_pct=stats.zero_clipped_pct,
        black_level=stats.black_level,
        effective_bit_depth=stats.effective_bit_depth,
        adc_max=stats.adc_max,
        bin_counts=counts,
        bin_edges=edges,
    )
