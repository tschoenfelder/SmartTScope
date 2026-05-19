"""Unit tests for pure helper functions in the workflow runner."""
import pytest

from smart_telescope.workflow.stages import _angular_offset_arcmin


class TestAngularOffsetArcmin:
    def test_zero_offset_for_identical_coords(self):
        assert _angular_offset_arcmin(5.5881, -5.391, 5.5881, -5.391) == pytest.approx(0.0)

    def test_pure_dec_offset_one_arcmin(self):
        # 1 arcmin = 1/60 degree in Dec; RA identical
        result = _angular_offset_arcmin(5.0, 0.0, 5.0, 1 / 60)
        assert result == pytest.approx(1.0, rel=0.01)

    def test_result_is_always_non_negative(self):
        # Swapping arguments must return the same magnitude
        a = _angular_offset_arcmin(5.5, -5.0, 5.6, -5.1)
        b = _angular_offset_arcmin(5.6, -5.1, 5.5, -5.0)
        assert a == pytest.approx(b, rel=0.001)
        assert a >= 0.0

    def test_ra_offset_accounts_for_cos_dec(self):
        # At Dec=60°, cos(60°)=0.5 so 1° RA offset ≈ 0.5° on sky = 30 arcmin
        result = _angular_offset_arcmin(1.0 / 15, 60.0, 0.0, 60.0)  # 1° RA apart
        assert result == pytest.approx(30.0, rel=0.05)

    def test_centering_tolerance_boundary(self):
        # 2 arcmin = 2/60 deg. A result just under 2 arcmin should pass the gate.
        tiny = 1.9 / 60  # 1.9 arcmin in degrees
        result = _angular_offset_arcmin(5.5881, -5.391, 5.5881, -5.391 + tiny)
        assert result < 2.0

    def test_large_offset_clearly_exceeds_tolerance(self):
        # ra=6.5, dec=-7.0 vs M42 — should be many arcminutes
        result = _angular_offset_arcmin(6.5, -7.0, 5.5881, -5.391)
        assert result > 30.0
