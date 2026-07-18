"""LiveAnalysis adapter shim — M10-004: SmartTScope-owned, thin.

Maps SmartTScope camera state to the external SmartTScopeLiveAnalysis
module's ``camera_info`` mapping and passes frames through
``analyze_camera_frame()``.  The external module is a pinned pip dependency
(see SYNC.md) — never edited locally; this shim is the only place that knows
its call signature.

Frame contract: ``FitsFrame.pixels`` is passed exactly as the camera adapter
delivered it.  The ToupTek adapters already right-shift MSB-aligned data to
the sensor's native ADC range and stamp the per-frame ``BITDEPTH`` header key
(12/14/16), so the frame is "native unscaled" by the time it reaches this
shim — no further scaling here.
"""
from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ..domain.frame import FitsFrame
    from ..ports.camera import CameraPort

_log = logging.getLogger(__name__)


def live_analysis_available() -> bool:
    """True when the pinned smarttscope_live_analysis package can be imported."""
    try:
        import smarttscope_live_analysis  # noqa: F401
        return True
    except ImportError:
        return False


def build_camera_info(
    camera: "CameraPort",
    *,
    frame: "FitsFrame | None" = None,
    binning: int = 1,
) -> dict[str, Any]:
    """Build the module's ``camera_info`` mapping from live camera state.

    Every field is best-effort: a camera that cannot report a value simply
    omits the key (the module treats missing values as unknown).  Per-frame
    facts win over camera-level queries — the frame's EXPTIME is the exposure
    that actually produced the pixels, and its BITDEPTH header reflects the
    detected pixel shift for exactly this frame.
    """
    info: dict[str, Any] = {"binning": int(binning), "raw_mode": True}

    exposure_s: float | None = None
    if frame is not None and frame.exposure_seconds > 0:
        exposure_s = float(frame.exposure_seconds)
    else:
        try:
            exposure_s = camera.get_exposure_ms() / 1000.0
        except Exception:
            pass
    if exposure_s is not None:
        info["exposure_s"] = exposure_s

    try:
        info["gain"] = int(camera.get_gain())
    except Exception:
        pass
    try:
        info["offset"] = int(camera.get_black_level())
    except Exception:
        pass

    bit_depth: int | None = None
    if frame is not None:
        try:
            raw = frame.header.get("BITDEPTH")  # type: ignore[attr-defined]
            if raw is not None:
                bit_depth = int(raw)
        except Exception:
            pass
    if bit_depth is None:
        try:
            bit_depth = int(camera.get_bit_depth())
        except Exception:
            pass
    if bit_depth is not None:
        info["bit_depth"] = bit_depth

    try:
        info["conversion_gain"] = camera.get_conversion_gain().name
    except Exception:
        pass

    return info


def analyze(
    camera_info: dict[str, Any],
    frame: "FitsFrame",
    previous_star_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run one frame through the external analyzer.

    Raises ImportError when the module is not installed — callers decide how
    to degrade (the setup FSM marks the camera DEGRADED, it never crashes).
    """
    from smarttscope_live_analysis import analyze_camera_frame

    return analyze_camera_frame(
        camera_info, frame.pixels, previous_star_state=previous_star_state,
    )
