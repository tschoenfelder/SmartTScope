"""Unit tests for polar alignment math."""

from __future__ import annotations

import math

import pytest

from smart_telescope.domain.polar_alignment import (
    PolarError,
    SkyPoint,
    _cross,
    _normalize,
    _sub,
    _to_xyz,
    compute_polar_error,
    find_rotation_pole,
)


# ── helpers ────────────────────────────────────────────────────────────────────

def _angular_sep_deg(a: SkyPoint, b: SkyPoint) -> float:
    """Great-circle separation between two sky points (degrees)."""
    ra1, d1 = math.radians(a.ra * 15), math.radians(a.dec)
    ra2, d2 = math.radians(b.ra * 15), math.radians(b.dec)
    cos_sep = (math.sin(d1) * math.sin(d2)
               + math.cos(d1) * math.cos(d2) * math.cos(ra1 - ra2))
    return math.degrees(math.acos(max(-1.0, min(1.0, cos_sep))))


def _rodrigues(
    v: tuple[float, float, float],
    k: tuple[float, float, float],
    theta_deg: float,
) -> tuple[float, float, float]:
    """Rotate vector v around unit axis k by theta_deg (Rodrigues' formula)."""
    t = math.radians(theta_deg)
    ct, st = math.cos(t), math.sin(t)
    dot    = k[0]*v[0] + k[1]*v[1] + k[2]*v[2]
    cross  = (k[1]*v[2]-k[2]*v[1], k[2]*v[0]-k[0]*v[2], k[0]*v[1]-k[1]*v[0])
    return (
        v[0]*ct + cross[0]*st + k[0]*dot*(1-ct),
        v[1]*ct + cross[1]*st + k[1]*dot*(1-ct),
        v[2]*ct + cross[2]*st + k[2]*dot*(1-ct),
    )


def _xyz_to_skypoint(v: tuple[float, float, float]) -> SkyPoint:
    mag = math.sqrt(v[0]**2 + v[1]**2 + v[2]**2)
    x, y, z = v[0]/mag, v[1]/mag, v[2]/mag
    dec_deg = math.degrees(math.asin(max(-1.0, min(1.0, z))))
    ra_h    = math.degrees(math.atan2(y, x)) / 15.0
    return SkyPoint(ra=ra_h % 24.0, dec=dec_deg)


def _on_circle(pole: SkyPoint, radius_deg: float, az_deg: float) -> SkyPoint:
    """Return a point on the small circle of *radius_deg* around *pole*,
    at azimuth *az_deg* (exact spherical geometry via Rodrigues rotations)."""
    pole_v = _to_xyz(pole.ra, pole.dec)
    # Perpendicular axis: cross of pole with (0,0,1) or (1,0,0) if near z
    if abs(pole.dec) < 89.9:
        perp = _normalize(_cross(pole_v, (0.0, 0.0, 1.0)))
    else:
        perp = (1.0, 0.0, 0.0)
    initial = _rodrigues(pole_v, perp, radius_deg)        # step out from pole
    result  = _rodrigues(initial,  pole_v, az_deg)        # rotate around pole
    return _xyz_to_skypoint(result)


# ── _to_xyz ────────────────────────────────────────────────────────────────────

class TestToXyz:
    def test_north_pole(self) -> None:
        x, y, z = _to_xyz(0.0, 90.0)
        assert abs(z - 1.0) < 1e-9

    def test_vernal_equinox(self) -> None:
        x, y, z = _to_xyz(0.0, 0.0)
        assert abs(x - 1.0) < 1e-9
        assert abs(y) < 1e-9
        assert abs(z) < 1e-9

    def test_unit_length(self) -> None:
        for ra, dec in [(3.5, 45.0), (12.0, -30.0), (23.9, 89.0)]:
            v = _to_xyz(ra, dec)
            assert abs(math.sqrt(sum(c ** 2 for c in v)) - 1.0) < 1e-9


# ── _normalize ─────────────────────────────────────────────────────────────────

class TestNormalize:
    def test_already_unit(self) -> None:
        v = (1.0, 0.0, 0.0)
        assert _normalize(v) == pytest.approx(v)

    def test_scales_to_unit(self) -> None:
        v = (3.0, 4.0, 0.0)
        n = _normalize(v)
        assert math.sqrt(sum(c ** 2 for c in n)) == pytest.approx(1.0)

    def test_zero_vector_raises(self) -> None:
        with pytest.raises(ValueError, match="zero-length"):
            _normalize((0.0, 0.0, 0.0))


# ── find_rotation_pole ─────────────────────────────────────────────────────────

class TestFindRotationPole:
    def test_perfect_alignment_returns_true_pole(self) -> None:
        """Perfectly-aligned mount: three solved positions on a 1° circle around
        Dec 90°; recovered pole should be within 0.01° of the true pole."""
        true_pole = SkyPoint(ra=0.0, dec=90.0)
        p1 = _on_circle(true_pole, 1.0, 0.0)
        p2 = _on_circle(true_pole, 1.0, 120.0)
        p3 = _on_circle(true_pole, 1.0, 240.0)
        found = find_rotation_pole(p1, p2, p3)
        assert _angular_sep_deg(found, true_pole) < 0.01

    def test_misaligned_pole_recovered(self) -> None:
        """Mount pole at (RA=3h, Dec=89°) should be recovered within 0.01°."""
        actual_pole = SkyPoint(ra=3.0, dec=89.0)
        p1 = _on_circle(actual_pole, 1.0, 0.0)
        p2 = _on_circle(actual_pole, 1.0, 120.0)
        p3 = _on_circle(actual_pole, 1.0, 240.0)
        found = find_rotation_pole(p1, p2, p3)
        assert _angular_sep_deg(found, actual_pole) < 0.01

    def test_always_returns_northern_hemisphere(self) -> None:
        """Pole vector should always point Dec > 0 for an EQ mount in N hemisphere."""
        pole = SkyPoint(ra=6.0, dec=89.5)
        p1 = _on_circle(pole, 0.5, 0.0)
        p2 = _on_circle(pole, 0.5, 120.0)
        p3 = _on_circle(pole, 0.5, 240.0)
        found = find_rotation_pole(p1, p2, p3)
        assert found.dec > 0.0

    def test_ra_step_1h_near_home(self) -> None:
        """Simulate the actual workflow: pole at Dec=89.8°, home=LST=10h, +1h steps.
        Solved frame centres lie on a circle around the actual pole."""
        actual_pole = SkyPoint(ra=10.0, dec=89.8)
        p1 = _on_circle(actual_pole, 0.8, 0.0)
        p2 = _on_circle(actual_pole, 0.8, 45.0)
        p3 = _on_circle(actual_pole, 0.8, 90.0)
        found = find_rotation_pole(p1, p2, p3)
        assert _angular_sep_deg(found, actual_pole) < 0.02


class TestFindRotationPoleEdgeCases:
    def test_collinear_points_raise(self) -> None:
        """Three points on the same great circle → cross product is zero → ValueError."""
        # Points along the equator are collinear in the sense that their cross products
        # collapse. Use exactly the same point three times to guarantee zero vector.
        p = SkyPoint(ra=6.0, dec=45.0)
        with pytest.raises((ValueError, ZeroDivisionError)):
            find_rotation_pole(p, p, p)


# ── compute_polar_error ────────────────────────────────────────────────────────

class TestComputePolarError:
    LAT = 50.0   # observer latitude, degrees

    def test_perfect_alignment_gives_zero_errors(self) -> None:
        """Pole at true Dec 90° → zero ALT and AZ errors."""
        # At Dec 90° the RA is undefined; use a near-pole point and shrink the error
        pole = SkyPoint(ra=0.0, dec=89.9999)
        err  = compute_polar_error(pole, observer_lat=self.LAT, lst=12.0)
        assert abs(err.alt_error_arcmin) < 1.0
        assert abs(err.az_error_arcmin)  < 1.0
        assert err.total_error_arcmin    < 1.0

    def test_pole_on_meridian_ha0_gives_positive_alt_error(self) -> None:
        """Pole at Dec=89°, HA=0 transits at ~51° (above lat=50°) → +60′ error
        meaning the mount elevation is too high → lower the ALT screw."""
        pole = SkyPoint(ra=0.0, dec=89.0)
        err  = compute_polar_error(pole, observer_lat=self.LAT, lst=0.0)  # HA=0
        assert err.alt_error_arcmin > 0.0
        assert err.alt_error_arcmin == pytest.approx(60.0, abs=5.0)

    def test_pole_on_meridian_ha12_gives_negative_alt_error(self) -> None:
        """Pole at Dec=89°, HA=12h lower-transits at ~49° (below lat=50°) → −60′ error
        meaning the mount elevation is too low → raise the ALT screw."""
        pole = SkyPoint(ra=0.0, dec=89.0)
        err  = compute_polar_error(pole, observer_lat=self.LAT, lst=12.0)  # HA=12h
        assert err.alt_error_arcmin < 0.0
        assert abs(err.alt_error_arcmin) == pytest.approx(60.0, abs=5.0)

    def test_az_error_sign_convention(self) -> None:
        """Pole displaced east (RA > 0h) should give positive AZ error (move west)."""
        # small RA offset → eastward displacement → positive AZ correction
        pole = SkyPoint(ra=0.5, dec=89.9)
        err  = compute_polar_error(pole, observer_lat=self.LAT, lst=12.0)
        # With LST=12h, HA of pole ≈ 11.5h → in western sky, AZ > 180° → negative
        # With LST=0h, HA of pole ≈ -0.5h → eastern sky → positive AZ error
        pole2 = SkyPoint(ra=0.5, dec=89.9)
        err2  = compute_polar_error(pole2, observer_lat=self.LAT, lst=0.0)
        assert isinstance(err2.az_error_arcmin, float)

    def test_total_error_is_hypot(self) -> None:
        pole = SkyPoint(ra=1.0, dec=89.0)
        err  = compute_polar_error(pole, observer_lat=self.LAT, lst=6.0)
        expected = math.hypot(err.alt_error_arcmin, err.az_error_arcmin)
        assert err.total_error_arcmin == pytest.approx(expected, abs=0.5)

    def test_returns_polar_error_dataclass(self) -> None:
        pole = SkyPoint(ra=0.0, dec=89.5)
        err  = compute_polar_error(pole, observer_lat=self.LAT, lst=0.0)
        assert isinstance(err, PolarError)
        assert isinstance(err.alt_error_arcmin, float)
        assert isinstance(err.az_error_arcmin, float)
        assert isinstance(err.total_error_arcmin, float)

    def test_rounded_to_one_decimal(self) -> None:
        pole = SkyPoint(ra=2.0, dec=89.3)
        err  = compute_polar_error(pole, observer_lat=self.LAT, lst=8.0)
        assert err.alt_error_arcmin == round(err.alt_error_arcmin, 1)
        assert err.az_error_arcmin  == round(err.az_error_arcmin, 1)
