"""Tests for StarAcquisition — Phase 5, Task 5.2."""
from __future__ import annotations

from typing import Iterator
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from smart_telescope.adapters.mock.mount import MockMount
from smart_telescope.domain.collimation.config import MountCenteringConfig
from smart_telescope.domain.frame import FitsFrame
from smart_telescope.ports.mount import MountState
from smart_telescope.services.collimation.mount_centering import PulseCenterer
from smart_telescope.services.collimation.star_acquisition import (
    AcquisitionResult,
    StarAcquisition,
)
from smart_telescope.services.collimation.star_selector import (
    BrightStar,
    CollimationStarCandidate,
)


# ── Frame helpers ─────────────────────────────────────────────────────────────

def _make_star_frame(
    cx: float = 128.0,
    cy: float = 128.0,
    width: int = 256,
    height: int = 256,
    peak_adu: float = 30_000.0,
    bg: float = 100.0,
    sigma: float = 3.0,
) -> FitsFrame:
    """Gaussian PSF star at (cx, cy) on a uniform noisy background.

    Use a 256×256 frame so the Gaussian blob stays under the 2% max-blob limit.
    """
    rng = np.random.default_rng(42)
    data = rng.normal(bg, 10.0, (height, width)).astype(np.float32)
    yy, xx = np.mgrid[0:height, 0:width]
    data += (peak_adu * np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * sigma ** 2))).astype(np.float32)
    return FitsFrame(pixels=data, header={}, exposure_seconds=1.0)


def _make_dim_frame(width: int = 256, height: int = 256) -> FitsFrame:
    """Uniform dim frame — no detectable star."""
    rng = np.random.default_rng(7)
    data = rng.normal(100.0, 10.0, (height, width)).astype(np.float32)
    return FitsFrame(pixels=data, header={}, exposure_seconds=1.0)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _candidate(name: str = "Vega", ra: float = 18.6, dec: float = 38.8, mag: float = 0.03, alt: float = 70.0) -> CollimationStarCandidate:
    star = BrightStar(name=name, ra_hours=ra, dec_deg=dec, magnitude=mag)
    return CollimationStarCandidate(star=star, altitude_deg=alt, azimuth_deg=180.0)


def _centering_cfg() -> MountCenteringConfig:
    return MountCenteringConfig(
        max_pulse_ms=500,
        settle_ms=0,
        fine_tolerance_px=5.0,
        rough_tolerance_px=20.0,
        initial_tolerance_px=50.0,
    )


def _centerer(mount=None) -> PulseCenterer:
    return PulseCenterer(
        mount=mount or MockMount(),
        config=_centering_cfg(),
        pixel_scale_arcsec=0.28,
        guide_rate_factor=0.5,
        max_iterations=10,
    )


def _mock_camera(frames: list[FitsFrame]) -> MagicMock:
    """Camera mock that returns frames sequentially from the list."""
    cam = MagicMock()
    cam.get_bit_depth.return_value = 16
    frame_iter: Iterator[FitsFrame] = iter(frames)
    cam.capture.side_effect = lambda _exp: next(frame_iter)
    return cam


def _acq(mount=None, camera=None, centerer=None) -> StarAcquisition:
    return StarAcquisition(
        mount=mount or MockMount(initial_state=MountState.TRACKING),
        camera=camera or _mock_camera([_make_star_frame()] * 20),
        centerer=centerer or _centerer(),
        exposure_seconds=1.0,
        settle_seconds=0.0,     # no sleep in tests
    )


# ── AcquisitionResult ─────────────────────────────────────────────────────────

class TestAcquisitionResult:
    def test_fields(self):
        r = AcquisitionResult(success=True, reason="ok", star_measurement=None, centering=None)
        assert r.success is True
        assert r.reason == "ok"
        assert r.star_measurement is None
        assert r.centering is None


# ── Successful acquisition ────────────────────────────────────────────────────

class TestSuccessfulAcquisition:
    def test_returns_ok_when_star_detected_and_centered(self):
        # Star at frame center (128,128) → centerer resolves "within_tolerance" immediately
        star_frame = _make_star_frame(cx=128.0, cy=128.0)  # already centered
        cam = _mock_camera([star_frame] * 20)
        acq = _acq(camera=cam)
        result = acq.acquire(_candidate())
        assert result.success is True
        assert result.reason == "ok"
        assert result.star_measurement is not None

    def test_star_measurement_populated(self):
        cam = _mock_camera([_make_star_frame()] * 20)
        acq = _acq(camera=cam)
        result = acq.acquire(_candidate())
        assert result.star_measurement is not None
        assert result.star_measurement.confidence > 0.0

    def test_centering_result_populated(self):
        cam = _mock_camera([_make_star_frame()] * 20)
        acq = _acq(camera=cam)
        result = acq.acquire(_candidate())
        assert result.centering is not None

    def test_mount_goto_called_with_star_coords(self):
        mount = MockMount(initial_state=MountState.TRACKING)
        cam = _mock_camera([_make_star_frame()] * 20)
        acq = _acq(mount=mount, camera=cam, centerer=_centerer(mount=mount))
        c = _candidate(ra=18.6, dec=38.8)
        acq.acquire(c)
        assert mount.get_position().ra  == pytest.approx(18.6)
        assert mount.get_position().dec == pytest.approx(38.8)

    def test_enables_tracking_after_slew(self):
        mount = MockMount(initial_state=MountState.UNPARKED)
        cam = _mock_camera([_make_star_frame()] * 20)
        acq = _acq(mount=mount, camera=cam, centerer=_centerer(mount=mount))
        acq.acquire(_candidate())
        assert mount.get_state() == MountState.TRACKING

    def test_tracking_already_set_stays_ok(self):
        mount = MockMount(initial_state=MountState.TRACKING)
        cam = _mock_camera([_make_star_frame()] * 20)
        acq = _acq(mount=mount, camera=cam, centerer=_centerer(mount=mount))
        result = acq.acquire(_candidate())
        assert result.success is True


# ── Slew failure ──────────────────────────────────────────────────────────────

class TestSlewFailure:
    def test_slew_failed_when_goto_returns_false(self):
        mount = MockMount(fail_goto=True, initial_state=MountState.UNPARKED)
        acq = _acq(mount=mount, centerer=_centerer(mount=mount))
        result = acq.acquire(_candidate())
        assert result.success is False
        assert result.reason == "slew_failed"
        assert result.star_measurement is None
        assert result.centering is None


# ── Star not found ────────────────────────────────────────────────────────────

class TestStarNotFound:
    def test_star_not_found_when_dim_frame(self):
        cam = _mock_camera([_make_dim_frame()] * 5)
        acq = _acq(camera=cam)
        result = acq.acquire(_candidate())
        assert result.success is False
        assert result.reason == "star_not_found"
        assert result.star_measurement is None
        assert result.centering is None


# ── Cancellation ──────────────────────────────────────────────────────────────

class TestCancellation:
    def test_cancelled_before_slew(self):
        acq = _acq()
        result = acq.acquire(_candidate(), cancel_check=lambda: True)
        assert result.success is False
        assert result.reason == "cancelled"

    def test_cancelled_after_settle(self):
        """cancel_check returns True after the slew (post-settle check)."""
        flags = {"count": 0}

        def _check() -> bool:
            flags["count"] += 1
            # First call: before slew → False (let slew proceed)
            # Second call: after settle → True (cancel)
            return flags["count"] >= 2

        cam = _mock_camera([_make_star_frame()] * 5)
        acq = _acq(camera=cam)
        result = acq.acquire(_candidate(), cancel_check=_check)
        assert result.success is False
        assert result.reason == "cancelled"

    def test_not_cancelled_returns_ok(self):
        cam = _mock_camera([_make_star_frame()] * 20)
        acq = _acq(camera=cam)
        result = acq.acquire(_candidate(), cancel_check=lambda: False)
        assert result.success is True


# ── Centering failure ─────────────────────────────────────────────────────────

class TestCenteringFailure:
    def test_centering_failed_returns_initial_measurement(self):
        """When centering diverges, the initial StarMeasurement is preserved."""
        mount = MockMount(initial_state=MountState.TRACKING)
        # First frame: star detected (initial). Subsequent frames: no star (lost during centering).
        frames = [_make_star_frame(cx=200.0, cy=128.0)] + [_make_dim_frame()] * 15
        cam = _mock_camera(frames)
        acq = _acq(
            mount=mount,
            camera=cam,
            centerer=_centerer(mount=mount),
        )
        result = acq.acquire(_candidate())
        assert result.success is False
        # Either "centering_failed" (star lost in centering → diverge/star_lost) or similar
        assert result.reason in ("centering_failed",)
        assert result.star_measurement is not None
