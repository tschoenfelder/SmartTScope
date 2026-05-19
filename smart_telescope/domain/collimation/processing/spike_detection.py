"""Tri-Bahtinov spike detection — Collimation Phase 10, COL-100.

Wraps the existing BahtinovAnalyzer to produce a SpikeMeasurement for the
collimation pipeline.  The analyzer is accepted as an argument so tests can
inject a mock without generating synthetic spike images.

Stop conditions
---------------
"ok"            : 3 spikes detected and measurement built.
"too_few_spikes": BahtinovAnalyzer raised ValueError (< 3 lines found).
"no_signal"     : analyzer returned zero confidence (degenerate frame).
"""
from __future__ import annotations

from dataclasses import dataclass

from ...bahtinov import BahtinovAnalyzer, CrossingAnalysisResult
from ..models import Point2D, SpikeMeasurement
from .frame import ProcessedFrame


@dataclass(frozen=True)
class SpikeDetectionResult:
    """Outcome of one spike-detection pass.

    raw_result is populated on "ok" and "no_signal" for overlay rendering.
    """
    measurement: SpikeMeasurement | None
    reason: str                              # see module docstring
    raw_result: CrossingAnalysisResult | None = None


def detect_spikes(
    processed: ProcessedFrame,
    ref_center: Point2D,
    analyzer: BahtinovAnalyzer | None = None,
) -> SpikeDetectionResult:
    """Run Bahtinov spike detection and build a SpikeMeasurement.

    Args:
        processed  : captured frame (only .mono array is used).
        ref_center : optical-axis reference point (from ReferenceCenterCalibration).
        analyzer   : BahtinovAnalyzer instance; a default one is created when None.

    Returns:
        SpikeDetectionResult with reason "ok" on success.
    """
    if analyzer is None:
        analyzer = BahtinovAnalyzer()

    try:
        result = analyzer.analyze(processed.mono)
    except ValueError:
        return SpikeDetectionResult(measurement=None, reason="too_few_spikes")

    if result.detection_confidence <= 0.0:
        return SpikeDetectionResult(
            measurement=None, reason="no_signal", raw_result=result
        )

    measurement = SpikeMeasurement.from_bahtinov_result(result, ref_center)
    return SpikeDetectionResult(
        measurement=measurement, reason="ok", raw_result=result
    )
