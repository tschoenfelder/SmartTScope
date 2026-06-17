"""POST /api/histogram/analyze — one-shot histogram from a live camera frame."""
from __future__ import annotations

import asyncio

import numpy as np
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..domain.histogram import HistogramStats, analyze, histogram_bins_focused
from . import deps

router = APIRouter(prefix="/api/histogram")


_LOW_ADU = 1000.0   # upper bound of the low-range pedestal histogram


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
    # Bin data for the UI histogram widget (focused range — right edge is hist_adu_hi)
    bin_counts: list[int]
    bin_edges: list[float]   # length = len(bin_counts) + 1
    hist_adu_hi: float       # ADU value at the right edge of the displayed histogram
    # Low-range pedestal histogram (0–1000 ADU, 100 bins, 10 ADU/bin)
    low_bin_counts: list[int]
    low_bin_edges: list[float]
    low_adu_hi: float


@router.post("/analyze", response_model=HistogramResponse)
async def analyze_histogram(
    camera_index: int = Query(default=0, ge=0, le=7),
    camera_role: str | None = Query(default=None),
    exposure: float = Query(default=2.0, gt=0.0, le=60.0),
    gain: int = Query(default=100, ge=0),
    offset: int = Query(default=0, ge=0, le=65535),
    bit_depth: int = Query(default=12, ge=8, le=16),
    n_bins: int = Query(default=512, ge=64, le=4096),
) -> HistogramResponse:
    """Capture one frame and return its histogram statistics and bin data."""
    try:
        camera = deps.get_preview_camera(deps.resolve_camera_index(camera_index, camera_role))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    camera.set_gain(gain)
    camera.set_black_level(offset)
    try:
        frame = await asyncio.to_thread(camera.capture, exposure)
    except RuntimeError as exc:
        status = 409 if "busy" in str(exc).lower() else 503
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Camera capture failed: {exc}") from exc

    # Use the bit depth reported in the frame header (camera detects native ADC depth
    # on first capture and right-shifts pixels to native range); fall back to the
    # query param if the header key is absent (e.g. replay/mock cameras).
    frame_bd = frame.header.get("BITDEPTH") if hasattr(frame.header, "get") else None
    if frame_bd is not None:
        bit_depth = int(frame_bd)

    stats: HistogramStats = analyze(frame.pixels, bit_depth=bit_depth)
    counts, edges, adu_hi = histogram_bins_focused(frame.pixels, bit_depth=bit_depth, n_bins=n_bins)

    adc_max = float((1 << bit_depth) - 1)
    normed = frame.pixels.astype(np.float64).ravel() / adc_max
    low_c, low_e = np.histogram(normed, bins=100, range=(0.0, _LOW_ADU / adc_max))

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
        hist_adu_hi=adu_hi,
        low_bin_counts=low_c.tolist(),
        low_bin_edges=low_e.tolist(),
        low_adu_hi=_LOW_ADU,
    )
