"""StarCountResult — shared return type for optional external frame analyzers.

Defines the data contract between SmartTScope and any external frame-analysis
module that implements the analyze_frame() interface.  The external module owns
the element type of 'sources'; SmartTScope code treats it as an opaque tuple.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

FrameQuality = Literal["usable", "too_dark", "too_bright", "stars_saturated"]


@dataclass(frozen=True)
class StarCountResult:
    """Result returned by an external frame analyzer.

    Fields
    ------
    stars_found:
        Number of point sources detected in the frame.
    image_quality:
        Coarse frame-quality label; one of the four FrameQuality values.
    suggested_exposure_s:
        Analyzer's suggestion for the next capture exposure (seconds).
        None means "no change recommended".
    suggested_gain:
        Analyzer's suggestion for the next camera gain value.
        None means "no change recommended".
    suggested_offset:
        Analyzer's suggestion for the next camera black-level offset.
        None means "no change recommended".
    focus_warning:
        True when the analyzer suspects focus or pointing issues.
    notes:
        Tuple of human-readable diagnostic messages from the analyzer.
    sources:
        Tuple of detected source objects.  The element type is owned by the
        external module; SmartTScope code never inspects individual items.
    """

    stars_found: int
    image_quality: FrameQuality
    suggested_exposure_s: float | None
    suggested_gain: int | None
    suggested_offset: int | None
    focus_warning: bool
    notes: tuple[str, ...]
    sources: tuple  # opaque — element type owned by the external analyzer
