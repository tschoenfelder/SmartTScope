"""Collimation optical train profiles — Task 0.3.

Defines C8 + camera combinations used by the collimation assistant.
Each profile carries the geometry constants needed by measurement algorithms:
  - focal length, aperture, secondary size
  - pixel size → pixel scale
  - focal ratio, central obstruction ratio

These profiles are collimation-assistant-specific.  They complement the
general-purpose OpticalTrainProfile in domain/optical_train.py (which focuses
on session / capture settings) and are not directly related.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CollimationOpticalProfile:
    """Optical train profile for the collimation assistant.

    profile_id matches the telescope_profile setting in [collimation] config.
    """
    profile_id: str
    focal_mm: float
    aperture_mm: float
    secondary_diameter_mm: float    # physical secondary mirror diameter
    pixel_size_um: float            # sensor pixel pitch
    camera_model: str

    @property
    def pixel_scale_arcsec(self) -> float:
        """Arcsec per pixel at this focal length (206.265 = arcsec/radian)."""
        return round(self.pixel_size_um * 206.265 / self.focal_mm, 4)

    @property
    def obstruction_ratio(self) -> float:
        """Central obstruction: secondary / primary diameter."""
        return round(self.secondary_diameter_mm / self.aperture_mm, 4)

    @property
    def focal_ratio(self) -> float:
        return round(self.focal_mm / self.aperture_mm, 2)

    def defocus_donut_inner_ratio(self) -> float:
        """Expected inner/outer radius ratio of the defocus donut.

        For a central obstruction ε = secondary_diameter / aperture,
        the inner dark hole has roughly ε × outer_radius at focus.
        (Indicative only; actual ratio depends on defocus amount.)
        """
        return self.obstruction_ratio


# ── C8 SCT profiles ───────────────────────────────────────────────────────────
# C8 specs: 203 mm aperture, f/10 native (2030 mm focal length).
# Secondary mirror: ~74 mm physical diameter → 36 % central obstruction.

C8_F10_678M = CollimationOpticalProfile(
    profile_id="c8_f10",            # default — matches config default
    focal_mm=2030.0,
    aperture_mm=203.0,
    secondary_diameter_mm=74.0,
    pixel_size_um=2.4,              # Touptek G3M678M
    camera_model="G3M678M",
)

C8_F10_ATR585M = CollimationOpticalProfile(
    profile_id="c8_f10_atr585m",
    focal_mm=2030.0,
    aperture_mm=203.0,
    secondary_diameter_mm=74.0,
    pixel_size_um=2.9,              # Touptek ATR585M
    camera_model="ATR585M",
)

# 0.63× reducer → 1280 mm effective focal length, f/6.3
C8_F6_3_678M = CollimationOpticalProfile(
    profile_id="c8_f6_3",
    focal_mm=1279.0,                # 2030 × 0.63
    aperture_mm=203.0,
    secondary_diameter_mm=74.0,
    pixel_size_um=2.4,
    camera_model="G3M678M",
)

# 2× Barlow → 4060 mm effective focal length, f/20
C8_F20_678M = CollimationOpticalProfile(
    profile_id="c8_f20_barlow2x",
    focal_mm=4060.0,                # 2030 × 2
    aperture_mm=203.0,
    secondary_diameter_mm=74.0,
    pixel_size_um=2.4,
    camera_model="G3M678M",
)

# ── Registry ──────────────────────────────────────────────────────────────────

ALL_PROFILES: dict[str, CollimationOpticalProfile] = {
    p.profile_id: p
    for p in (C8_F10_678M, C8_F10_ATR585M, C8_F6_3_678M, C8_F20_678M)
}


def get_profile(profile_id: str) -> CollimationOpticalProfile:
    """Return profile by id, defaulting to c8_f10 if not found."""
    return ALL_PROFILES.get(profile_id, C8_F10_678M)
