"""Maskless final validation — Collimation Phase 12, COL-121.

After the Tri-Bahtinov mask has been removed, assess whether the telescope
is correctly collimated by measuring the residual donut error.

Status values
-------------
"complete"               : error_ratio ≤ good_error_ratio and confidence ok.
"acceptable_with_warning": error_ratio ≤ fallback_error_ratio (marginal).
"seeing_limited"         : jitter too high for a definitive verdict; result
                           is the best estimate under current seeing.
"failed"                 : error_ratio > fallback_error_ratio, or confidence
                           below the minimum threshold.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ...domain.collimation.models import DonutMeasurement


@dataclass(frozen=True)
class ValidationReport:
    """Result of a final maskless collimation check.

    status           : verdict string (see module docstring).
    donut_error_px   : measured collimation error in pixels.
    donut_error_ratio: error relative to outer-ring mean radius (0–1 scale).
    is_collimated    : True when status is "complete".
    confidence       : detection confidence from the donut measurement (0–1).
    warnings         : list of human-readable advisory messages.
    """
    status: str
    donut_error_px: float
    donut_error_ratio: float
    is_collimated: bool
    confidence: float
    warnings: list[str] = field(default_factory=list)


class MasklessValidator:
    """Assess final collimation quality from a donut measurement.

    Args:
        good_error_ratio        : error/radius ≤ this → "complete" (default 0.02).
        fallback_error_ratio    : error/radius ≤ this → "acceptable_with_warning".
        min_confidence          : minimum detection confidence to trust result.
        seeing_jitter_threshold_px: jitter above this triggers "seeing_limited".
    """

    def __init__(
        self,
        good_error_ratio: float = 0.02,
        fallback_error_ratio: float = 0.05,
        min_confidence: float = 0.5,
        seeing_jitter_threshold_px: float = 3.0,
    ) -> None:
        self._good_ratio     = good_error_ratio
        self._fallback_ratio = fallback_error_ratio
        self._min_conf       = min_confidence
        self._seeing_thr     = seeing_jitter_threshold_px

    def assess(
        self,
        donut: DonutMeasurement,
        jitter_px: float = 0.0,
    ) -> ValidationReport:
        """Evaluate collimation quality from *donut* and optional seeing jitter.

        Args:
            donut     : DonutMeasurement from the defocused star image.
            jitter_px : peak-to-peak or RMS seeing jitter (px); 0 = not known.

        Returns:
            :class:`ValidationReport` describing the verdict and quality metrics.
        """
        outer_radius = (donut.outer_ring.radius_x + donut.outer_ring.radius_y) / 2.0
        error_px     = donut.error_magnitude_px
        error_ratio  = error_px / outer_radius if outer_radius > 0 else float("inf")
        confidence   = donut.confidence
        warnings: list[str] = []

        if confidence < self._min_conf:
            warnings.append(
                f"detection confidence {confidence:.2f} below minimum {self._min_conf:.2f}"
            )
            return ValidationReport(
                status="failed",
                donut_error_px=error_px,
                donut_error_ratio=error_ratio,
                is_collimated=False,
                confidence=confidence,
                warnings=warnings,
            )

        seeing_limited = jitter_px > self._seeing_thr
        if seeing_limited:
            warnings.append(
                f"seeing jitter {jitter_px:.1f} px exceeds threshold "
                f"{self._seeing_thr:.1f} px — result may be unreliable"
            )

        if error_ratio <= self._good_ratio:
            status = "seeing_limited" if seeing_limited else "complete"
            is_collimated = not seeing_limited
        elif error_ratio <= self._fallback_ratio:
            status = "seeing_limited" if seeing_limited else "acceptable_with_warning"
            is_collimated = False
            if not seeing_limited:
                warnings.append(
                    f"error ratio {error_ratio:.3f} exceeds good threshold "
                    f"{self._good_ratio:.3f} — consider another iteration"
                )
        else:
            status = "failed"
            is_collimated = False
            warnings.append(
                f"error ratio {error_ratio:.3f} exceeds fallback threshold "
                f"{self._fallback_ratio:.3f} — collimation correction required"
            )

        return ValidationReport(
            status=status,
            donut_error_px=error_px,
            donut_error_ratio=error_ratio,
            is_collimated=is_collimated,
            confidence=confidence,
            warnings=warnings,
        )
