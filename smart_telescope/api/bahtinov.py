"""Bahtinov mask analysis API — POST /api/bahtinov/analyze."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..domain.bahtinov import BahtinovAnalyzer
from ..ports.camera import CameraPort
from . import deps

router = APIRouter(prefix="/api/bahtinov")


class AnalyzeRequest(BaseModel):
    exposure: float = 0.5
    gain:     int   = 100


@router.post("/analyze")
def bahtinov_analyze(
    body:   AnalyzeRequest,
    camera: CameraPort = Depends(deps.get_camera),
) -> dict[str, object]:
    """Capture one frame and run the Bahtinov spike analyzer.

    Returns CrossingAnalysisResult fields plus image_size_px so the client
    can map pixel coordinates to displayed image coordinates.
    """
    frame = camera.capture(exposure_seconds=body.exposure)

    try:
        result = BahtinovAnalyzer().analyze(frame.pixels)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    d = result.to_dict()
    h, w = frame.pixels.shape[:2]
    d["image_size_px"] = [w, h]
    return d
