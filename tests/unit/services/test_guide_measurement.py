import numpy as np
import pytest

from smart_telescope.domain.guiding import GuideSourceHealth

pytest.importorskip("smart_telescope.services.guide_measurement", reason="guide_measurement not yet implemented")
from smart_telescope.services.guide_measurement import (  # noqa: E402
    CentroidConfig,
    GuideCentroidEstimator,
    GuideSourceSelector,
    MeasureOnlyGuideController,
    source_state_from_measurement,
)


def _star_frame(x: float, y: float, shape=(80, 100), sigma=2.0, amplitude=2000.0, background=100.0):
    yy, xx = np.indices(shape, dtype=np.float32)
    pixels = background + amplitude * np.exp(-(((xx - x) ** 2 + (yy - y) ** 2) / (2.0 * sigma**2)))
    return pixels.astype(np.uint16)


def test_centroid_accepts_clean_star():
    estimator = GuideCentroidEstimator(CentroidConfig(roi_px=24, min_peak_snr=5.0))
    result = estimator.measure(_star_frame(40.25, 30.75), role="guide", sequence=1)

    assert result.accepted
    assert result.centroid_x is not None
    assert result.centroid_y is not None
    assert abs(result.centroid_x - 40.25) < 0.2
    assert abs(result.centroid_y - 30.75) < 0.2
    assert result.error_x == 0.0
    assert result.error_y == 0.0


def test_centroid_rejects_saturated_star():
    pixels = _star_frame(40, 30)
    pixels[30, 40] = np.iinfo(np.uint16).max
    estimator = GuideCentroidEstimator(CentroidConfig(roi_px=24))

    result = estimator.measure(pixels, role="guide", sequence=1)

    assert not result.accepted
    assert result.saturated
    assert "saturated" in (result.rejected_reason or "")


def test_measure_only_controller_outputs_would_pulses():
    estimator = GuideCentroidEstimator(CentroidConfig(roi_px=24))
    target = estimator.measure(_star_frame(40, 30), role="guide", sequence=1)
    shifted = estimator.measure(
        _star_frame(42, 29),
        role="guide",
        sequence=2,
        target=(target.centroid_x, target.centroid_y),
    )
    controller = MeasureOnlyGuideController()

    pulses = controller.would_pulse(shifted)

    assert len(pulses) == 2
    assert {pulse.axis for pulse in pulses} == {"ra", "dec"}


def test_source_selector_prefers_primary_then_fallback():
    selector = GuideSourceSelector(primary_role="guide", allow_fallback=True)
    estimator = GuideCentroidEstimator()
    good = estimator.measure(_star_frame(40, 30), role="oag", sequence=1)
    bad = estimator.measure(np.zeros((20, 20), dtype=np.uint16), role="guide", sequence=1)
    states = {
        "guide": source_state_from_measurement(
            "guide",
            bad,
            running=True,
            latest_sequence=1,
            latest_frame_age_s=0.1,
            bad_frame_count=3,
            fallback_after_bad_frames=3,
        ),
        "oag": source_state_from_measurement(
            "oag",
            good,
            running=True,
            latest_sequence=1,
            latest_frame_age_s=0.1,
            bad_frame_count=0,
            fallback_after_bad_frames=3,
        ),
    }

    assert states["guide"].health == GuideSourceHealth.TRANSIENT_BAD
    assert selector.select(states) == "oag"
    assert selector.reason == "fallback_from_guide"
