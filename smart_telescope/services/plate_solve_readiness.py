"""Plate-solve readiness pre-check service (M8-020 / REQ-PS-001).

Evaluates all 8 conditions in order and logs the result to the plate_solve
section logger.  Each unsatisfied condition provides a specific failure reason.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .section_logger import SectionLogger

from ..domain.plate_solve_readiness import (
    PlateSolveReadinessResult,
    ReadinessCondition,
)

_log = logging.getLogger(__name__)


def check_plate_solve_readiness(
    *,
    frame_pixels: "Any | None" = None,        # np.ndarray of captured frame (2-D)
    frame_fits_path: "str | None" = None,     # path if frame was saved as FITS
    star_count: "int | None" = None,          # from last _analyse_frame call
    optical_train_name: "str | None" = None,  # name of the active optical train
    pixel_scale_arcsec: "float | None" = None,# from optical train config
    focal_length_mm: "float | None" = None,   # from optical train config
    search_radius_deg: "float | None" = None, # alternative to focal_length
    astap_found: bool = False,                 # ASTAP executable located
    catalog_found: bool = False,               # ASTAP star catalog located
    gate_allows: bool = True,                  # operation gate result
    gate_reason: "str | None" = None,         # populated when gate_allows=False
    section_logger: "SectionLogger | None" = None,
) -> PlateSolveReadinessResult:
    """Evaluate all 8 plate-solve readiness conditions.

    Args:
        frame_pixels:        Latest captured frame array; None = no frame captured yet.
        frame_fits_path:     Path to saved FITS file; None = frame not persisted.
        star_count:          Estimated star count from last frame analysis; None = not measured.
        optical_train_name:  Active optical train name; None = no train configured.
        pixel_scale_arcsec:  Pixel scale from optical train; None = not configured.
        focal_length_mm:     Focal length in mm; None = not configured.
        search_radius_deg:   ASTAP search radius hint; substitutes for focal_length.
        astap_found:         ASTAP executable is accessible.
        catalog_found:       ASTAP star catalog is accessible.
        gate_allows:         Operation gate allows a plate solve now.
        gate_reason:         Rejection reason when gate_allows=False.
        section_logger:      If provided, writes the JSON-line result to plate_solve section.

    Returns:
        PlateSolveReadinessResult with one ReadinessCondition per check.
    """
    conditions: list[ReadinessCondition] = []

    # 1. frame_exists
    conditions.append(ReadinessCondition(
        name="frame_exists",
        satisfied=frame_pixels is not None,
        reason=None if frame_pixels is not None else "No frame captured yet — run a preview capture first",
    ))

    # 2. frame_saved_as_fits
    conditions.append(ReadinessCondition(
        name="frame_saved_as_fits",
        satisfied=frame_fits_path is not None,
        reason=None if frame_fits_path is not None else "Frame not saved as FITS — enable diagnostic frame storage",
    ))

    # 3. optical_train_metadata_available
    conditions.append(ReadinessCondition(
        name="optical_train_metadata_available",
        satisfied=optical_train_name is not None,
        reason=None if optical_train_name is not None else "No optical train configured — add a train in the configuration",
    ))

    # 4. pixel_size_available
    conditions.append(ReadinessCondition(
        name="pixel_size_available",
        satisfied=pixel_scale_arcsec is not None,
        reason=None if pixel_scale_arcsec is not None else "Pixel scale (arcsec/px) not set in optical train — add pixel_size_um and focal_length_mm",
    ))

    # 5. focal_length_or_hint_available
    focal_hint_ok = focal_length_mm is not None or search_radius_deg is not None
    conditions.append(ReadinessCondition(
        name="focal_length_or_hint_available",
        satisfied=focal_hint_ok,
        reason=None if focal_hint_ok else "Focal length (mm) or search radius (deg) not configured — ASTAP needs this to constrain the search",
    ))

    # 6. star_count_measured
    conditions.append(ReadinessCondition(
        name="star_count_measured",
        satisfied=star_count is not None,
        reason=None if star_count is not None else "Star count not measured — run a preview capture with frame analysis enabled",
    ))

    # 7. astap_available
    astap_ok = astap_found and catalog_found
    if not astap_found:
        astap_reason = "ASTAP executable not found — install ASTAP and add to PATH"
    elif not catalog_found:
        astap_reason = "ASTAP star catalog not found — download the D80 catalog"
    else:
        astap_reason = None
    conditions.append(ReadinessCondition(
        name="astap_available",
        satisfied=astap_ok,
        reason=astap_reason,
    ))

    # 8. operation_gate_allows_plate_solve
    conditions.append(ReadinessCondition(
        name="operation_gate_allows_plate_solve",
        satisfied=gate_allows,
        reason=None if gate_allows else (gate_reason or "Operation gate blocked plate solve"),
    ))

    ready = all(c.satisfied for c in conditions)
    result = PlateSolveReadinessResult(ready=ready, conditions=conditions)

    if section_logger is not None:
        try:
            section_logger.get("plate_solve").info("%s", result.to_json_line())
        except Exception as exc:
            _log.warning("Failed to log plate-solve readiness: %s", exc)

    return result
