"""Collimation assistant domain models — Tasks 0.2 + 0.3.

All models are pure dataclasses: no hardware dependencies, no UI imports.
All measurement models carry a confidence field (0–1).
All recommendation models carry screw_id, direction, size, reason, confidence.

Reference-center abstraction (Task 0.3):
  ReferenceCenterCalibration.compute(width, height) → (cx, cy)
  Default (frame_center source): returns frame center regardless of offset.
  Calibrated source: returns frame_center + configured offset.
"""
from __future__ import annotations

import dataclasses
import enum
import math
from typing import NamedTuple


# ── Geometry primitives ───────────────────────────────────────────────────────

class Point2D(NamedTuple):
    """Pixel coordinate (x = column, y = row)."""
    x: float
    y: float

    def distance_to(self, other: Point2D) -> float:
        return math.hypot(self.x - other.x, self.y - other.y)

    def __sub__(self, other: object) -> Point2D:  # type: ignore[override]
        if not isinstance(other, Point2D):
            return NotImplemented
        return Point2D(self.x - other.x, self.y - other.y)


# ── Enums ─────────────────────────────────────────────────────────────────────

class TurnDirection(str, enum.Enum):
    CLOCKWISE         = "clockwise"
    COUNTER_CLOCKWISE = "counter_clockwise"
    NONE              = "none"


class AdjustmentSize(str, enum.Enum):
    LARGE  = "large"    # > ¼ turn
    MEDIUM = "medium"   # ⅛–¼ turn
    SMALL  = "small"    # < ⅛ turn
    NONE   = "none"


class SessionPhase(str, enum.Enum):
    IDLE               = "idle"
    STAR_SELECTION     = "star_selection"
    STAR_CENTERING     = "star_centering"
    ROUGH_FOCUS        = "rough_focus"
    ROUGH_COLLIMATION  = "rough_collimation"
    FINE_FOCUS         = "fine_focus"
    FINE_COLLIMATION   = "fine_collimation"
    VALIDATION         = "validation"
    DONE               = "done"
    FAILED             = "failed"
    CONTRADICTION      = "contradiction"


# ── Reference-center abstraction (Task 0.3) ───────────────────────────────────

@dataclasses.dataclass(frozen=True)
class ReferenceCenterCalibration:
    """Optical-axis reference calibration.

    source='frame_center' (MVP default): reference == frame center;
        offset_x/y are ignored.
    source='calibrated': reference = frame_center + (offset_x_px, offset_y_px).
        The offset is the measured displacement from the geometric frame center
        to the true optical axis center, stored per optical-train profile.

    Both UI and donut/spike measurement algorithms must use .compute() instead
    of hard-coding frame_width/2 as the reference.
    """
    offset_x_px: float = 0.0
    offset_y_px: float = 0.0
    source: str = "frame_center"  # "frame_center" | "calibrated"

    def compute(self, frame_width: int, frame_height: int) -> Point2D:
        """Return reference center in image pixel coordinates.

        Always safe to call: falls back to frame center when source is
        'frame_center' or offset is zero.
        """
        cx = frame_width  / 2.0
        cy = frame_height / 2.0
        if self.source == "calibrated":
            cx += self.offset_x_px
            cy += self.offset_y_px
        return Point2D(cx, cy)

    @property
    def is_calibrated(self) -> bool:
        return self.source == "calibrated"

    @property
    def has_offset(self) -> bool:
        return self.offset_x_px != 0.0 or self.offset_y_px != 0.0


# ── Fitted geometry ───────────────────────────────────────────────────────────

@dataclasses.dataclass(frozen=True)
class CircleEllipseFit:
    """Fitted circle or ellipse in image pixel coordinates.

    Used for donut outer-ring / inner-hole fitting and daylight concentricity checks.
    """
    center_x: float
    center_y: float
    radius_x: float          # semi-major axis (pixels); for circles == radius_y
    radius_y: float          # semi-minor axis (pixels)
    angle_deg: float = 0.0   # major-axis rotation, 0 = horizontal
    confidence: float = 0.0  # 0–1; fit quality

    @property
    def center(self) -> Point2D:
        return Point2D(self.center_x, self.center_y)

    @property
    def is_circle(self) -> bool:
        """True when ellipse is close enough to circular (< 5 % difference)."""
        if self.radius_x <= 0 or self.radius_y <= 0:
            return True
        ratio = min(self.radius_x, self.radius_y) / max(self.radius_x, self.radius_y)
        return ratio >= 0.95

    @property
    def eccentricity(self) -> float:
        a = max(self.radius_x, self.radius_y)
        b = min(self.radius_x, self.radius_y)
        if a <= 0:
            return 0.0
        return math.sqrt(1.0 - (b / a) ** 2)

    @property
    def mean_radius(self) -> float:
        return (self.radius_x + self.radius_y) / 2.0


# ── Raw measurements ──────────────────────────────────────────────────────────

@dataclasses.dataclass(frozen=True)
class StarMeasurement:
    """Basic star position and PSF measurement from a single frame."""
    center_x: float
    center_y: float
    fwhm_px: float
    peak_adu: float
    total_flux: float
    snr: float
    confidence: float   # 0–1; detection quality

    @property
    def center(self) -> Point2D:
        return Point2D(self.center_x, self.center_y)


@dataclasses.dataclass(frozen=True)
class DonutMeasurement:
    """Defocused-star (donut) measurement for rough SCT collimation.

    The inner hole of a defocused C8 image is the shadow of the secondary mirror.
    Its center relative to the outer ring center indicates the collimation error:
      error_vector = inner_hole.center - outer_ring.center
    A well-collimated scope has this vector close to (0, 0).
    """
    outer_ring: CircleEllipseFit   # bright outer ring of the donut
    inner_hole: CircleEllipseFit   # dark inner hole (secondary shadow)
    error_x_px: float              # inner_hole.center_x - outer_ring.center_x
    error_y_px: float              # inner_hole.center_y - outer_ring.center_y
    error_magnitude_px: float      # sqrt(error_x² + error_y²)
    error_angle_deg: float         # direction of error vector (0° = right/+x)
    confidence: float              # 0–1

    @property
    def error_vector(self) -> Point2D:
        return Point2D(self.error_x_px, self.error_y_px)

    @property
    def is_collimated(self) -> bool:
        """True when error < 2 % of outer ring radius (good_error_ratio default)."""
        r = self.outer_ring.mean_radius
        return r > 0 and (self.error_magnitude_px / r) < 0.02


@dataclasses.dataclass(frozen=True)
class SpikeMeasurement:
    """Tri-Bahtinov spike measurement for fine collimation.

    Computed from a BahtinovAnalyzer CrossingAnalysisResult and augmented
    with the reference-center context for this frame.
    """
    focus_error_px: float           # signed; 0 = in focus (primary metric)
    crossing_error_rms_px: float    # crossing consistency; < 2 px is good
    crossing_point_x: float         # crossing point in image pixel coords
    crossing_point_y: float
    reference_center_x: float       # reference center used for this measurement
    reference_center_y: float
    offset_from_ref_px: float       # |crossing_point - reference_center|
    confidence: float               # min spike-line confidence (0–1)

    @property
    def crossing_point(self) -> Point2D:
        return Point2D(self.crossing_point_x, self.crossing_point_y)

    @property
    def reference_center(self) -> Point2D:
        return Point2D(self.reference_center_x, self.reference_center_y)

    @property
    def is_in_focus(self) -> bool:
        return abs(self.focus_error_px) <= 1.5

    @classmethod
    def from_bahtinov_result(
        cls,
        result: object,   # CrossingAnalysisResult — avoid circular import
        ref_center: Point2D,
    ) -> SpikeMeasurement:
        """Build from a CrossingAnalysisResult (bahtinov domain)."""
        cx, cy = result.common_crossing_point_px  # type: ignore[union-attr]
        offset = math.hypot(cx - ref_center.x, cy - ref_center.y)
        return cls(
            focus_error_px=result.focus_error_px,  # type: ignore[union-attr]
            crossing_error_rms_px=result.crossing_error_rms_px,  # type: ignore[union-attr]
            crossing_point_x=cx,
            crossing_point_y=cy,
            reference_center_x=ref_center.x,
            reference_center_y=ref_center.y,
            offset_from_ref_px=offset,
            confidence=result.detection_confidence,  # type: ignore[union-attr]
        )


@dataclasses.dataclass(frozen=True)
class FrameMeasurement:
    """Aggregated measurements from one captured frame.

    Which fields are populated depends on the session phase:
    - rough collimation: star + donut
    - fine collimation:  star + spike
    All populated measurements carry a confidence value.
    """
    frame_index: int
    captured_at: str            # ISO-8601
    exposure_s: float
    gain: int
    star: StarMeasurement | None = None
    donut: DonutMeasurement | None = None
    spike: SpikeMeasurement | None = None
    reference_center: ReferenceCenterCalibration | None = None

    @property
    def confidence(self) -> float:
        """Minimum confidence across all populated measurements."""
        confs = [
            m.confidence
            for m in (self.star, self.donut, self.spike)
            if m is not None
        ]
        return min(confs) if confs else 0.0


# ── Collimation guidance ──────────────────────────────────────────────────────

@dataclasses.dataclass(frozen=True)
class CollimationRecommendation:
    """One actionable screw-turn recommendation.

    All fields are required — per Phase 0 acceptance criteria every
    recommendation must carry screw_id, turn_direction, adjustment_size,
    reason, and confidence.
    """
    screw_id: str                        # "T1", "T2", "T3" (SCT tilt screws)
    turn_direction: TurnDirection
    adjustment_size: AdjustmentSize
    reason: str                          # human-readable explanation
    confidence: float                    # 0–1; below 0.5 → display warning only

    @property
    def is_actionable(self) -> bool:
        """True when confidence is high enough to show as a command (not just a hint)."""
        return self.confidence >= 0.5 and self.turn_direction != TurnDirection.NONE


@dataclasses.dataclass(frozen=True)
class ScrewCalibration:
    """Learned response of one collimation screw.

    Populated by observing how a unit CW turn shifts the donut/crossing center.
    Used to weight recommendations toward higher-confidence screws.
    """
    screw_id: str
    response_vector_x: float    # px shift per small CW turn (image x-axis)
    response_vector_y: float    # px shift per small CW turn (image y-axis)
    samples: int                # number of observations averaged
    confidence: float           # 0–1; increases with samples

    @property
    def response_magnitude(self) -> float:
        return math.hypot(self.response_vector_x, self.response_vector_y)


@dataclasses.dataclass(frozen=True)
class MaskSectorCalibration:
    """Maps Tri-Bahtinov mask sectors to physical collimation screws.

    Calibrated once per physical setup (mask orientation relative to screw
    positions on the scope).  Needed to translate a spike error direction
    into the correct screw to turn.
    """
    sector_0_deg: str     # screw controlling the spike sector at 0°
    sector_120_deg: str   # screw controlling the spike sector at 120°
    sector_240_deg: str   # screw controlling the spike sector at 240°
    calibrated_at: str    # ISO-8601


# ── Contradiction detection ───────────────────────────────────────────────────

@dataclasses.dataclass(frozen=True)
class ContradictionAssessment:
    """Conflict detection across measurement sources.

    When contradictions are found the assistant must stop issuing screw-turn
    commands and ask the user to remeasure or investigate.  The stop_guidance
    flag gates the next screw hint in the workflow.
    """
    has_contradiction: bool
    conflicting_indicators: list[str]   # human-readable descriptions of conflicts
    stop_guidance: bool                 # True = block next screw hint
    recommended_action: str             # e.g. "Recenter star and remeasure"
    confidence: float                   # 0–1; confidence in the contradiction itself


# ── Mechanical alignment — daylight / OCAL-like, non-MVP ─────────────────────

@dataclasses.dataclass(frozen=True)
class MechanicalCircleMeasurement:
    """One mechanical feature (tube edge, baffle ring) measured in an image."""
    label: str                    # e.g. "tube_edge", "secondary_baffle"
    fit: CircleEllipseFit
    is_rough_pre_check_only: bool = True   # always True — see warning below


@dataclasses.dataclass(frozen=True)
class MechanicalAlignmentReport:
    """Daylight mechanical concentricity pre-check (non-MVP, always rough).

    rough_pre_check_only is always True.  This report must never be used as
    a substitute for final star-based optical collimation verification.
    """
    circles: list[MechanicalCircleMeasurement]
    concentricity_error_px: float   # max center offset across all circles
    is_concentric: bool             # True when error < threshold
    rough_pre_check_only: bool = True
    warning: str = (
        "Mechanical concentricity is only a rough pre-check; "
        "final SCT collimation requires star validation."
    )
