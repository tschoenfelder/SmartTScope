"""Rough donut overlay data builder — Collimation Phase 7, COL-072.

Converts a DonutMeasurement into a DonutOverlay that the UI can render:
  – outer ring circle
  – inner hole circle
  – error vector arrow
  – traffic-light status (green / yellow / red)
  – three rough screw marker positions (T1 / T2 / T3)

No rendering is done here; this module produces structured data only.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from ...domain.collimation.models import DonutMeasurement

# Error / outer-radius ratio thresholds for the traffic light
_GREEN_RATIO  = 0.02   # < 2 %  → well collimated
_YELLOW_RATIO = 0.10   # 2–10 % → minor adjustment needed

# Screw markers are placed at this multiple of the outer radius
_SCREW_OFFSET_FACTOR = 1.25


@dataclass(frozen=True)
class ScrewMarker:
    """Rough collimation screw marker for UI overlay.

    Positions are approximate (uncalibrated until Phase 8).
    angle_deg follows image convention: 0° = +x (right), 90° = +y (down).
    """
    label: str          # "T1", "T2", "T3"
    position_x: float   # pixel column
    position_y: float   # pixel row
    angle_deg: float    # angle from outer ring center


@dataclass(frozen=True)
class DonutOverlay:
    """All data needed to render the rough collimation overlay.

    Coordinates are image pixels (x = col, y = row, origin = top-left).
    """
    outer_center_x: float
    outer_center_y: float
    outer_radius_px: float
    inner_center_x: float
    inner_center_y: float
    inner_radius_px: float
    error_x_px: float
    error_y_px: float
    error_magnitude_px: float
    error_angle_deg: float
    traffic_light: str          # "green" | "yellow" | "red"
    screws: list[ScrewMarker]
    confidence: float


def build_donut_overlay(
    measurement: DonutMeasurement,
    screw_angles_deg: tuple[float, float, float] = (90.0, 210.0, 330.0),
) -> DonutOverlay:
    """Build overlay data from a DonutMeasurement.

    Args:
        measurement      : populated DonutMeasurement (reason == "ok").
        screw_angles_deg : angles for T1, T2, T3 markers in image degrees
                           (0° = right, 90° = down).  Default (90°, 210°, 330°)
                           places T1 at the bottom, T2 upper-right, T3 upper-left
                           — a common C8 rear-screw layout.

    Returns:
        DonutOverlay with all fields populated.
    """
    outer = measurement.outer_ring
    inner = measurement.inner_hole

    # Traffic light based on error / outer_radius ratio
    outer_r = max(outer.mean_radius, 1.0)
    ratio   = measurement.error_magnitude_px / outer_r
    if ratio < _GREEN_RATIO:
        traffic_light = "green"
    elif ratio < _YELLOW_RATIO:
        traffic_light = "yellow"
    else:
        traffic_light = "red"

    # Screw markers placed at outer_radius × SCREW_OFFSET_FACTOR
    marker_r = outer_r * _SCREW_OFFSET_FACTOR
    screws = [
        ScrewMarker(
            label=f"T{i + 1}",
            position_x=outer.center_x + marker_r * math.cos(math.radians(angle)),
            position_y=outer.center_y + marker_r * math.sin(math.radians(angle)),
            angle_deg=angle,
        )
        for i, angle in enumerate(screw_angles_deg)
    ]

    return DonutOverlay(
        outer_center_x=outer.center_x,
        outer_center_y=outer.center_y,
        outer_radius_px=outer.mean_radius,
        inner_center_x=inner.center_x,
        inner_center_y=inner.center_y,
        inner_radius_px=inner.mean_radius,
        error_x_px=measurement.error_x_px,
        error_y_px=measurement.error_y_px,
        error_magnitude_px=measurement.error_magnitude_px,
        error_angle_deg=measurement.error_angle_deg,
        traffic_light=traffic_light,
        screws=screws,
        confidence=measurement.confidence,
    )
