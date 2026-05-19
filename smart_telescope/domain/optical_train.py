"""Optical train profiles — describes the telescope + reducer/barlow + camera combinations.

Pixel scale formula: scale_arcsec = pixel_um * 206.265 / focal_mm
(206.265 = 1 radian in arcseconds)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class TrainRole(str, Enum):
    DSO       = "dso"
    PLANETARY = "planetary"
    LUNAR     = "lunar"
    GUIDING   = "guiding"
    GENERAL   = "general"


@dataclass(frozen=True)
class OpticalTrainProfile:
    profile_id: str
    focal_mm: float
    camera_model: str
    pixel_scale_arcsec: float
    roles: frozenset[TrainRole] = field(default_factory=frozenset)

    @staticmethod
    def compute_scale(pixel_um: float, focal_mm: float) -> float:
        """Return pixel scale in arcsec/px (206.265 = arcsec per radian)."""
        return round(pixel_um * 206.265 / focal_mm, 4)


# ── C8 + ATR585M ──────────────────────────────────────────────────────────────

C8_NATIVE_ATR585M = OpticalTrainProfile(
    profile_id="C8_NATIVE_ATR585M",
    focal_mm=2030.0,
    camera_model="ATR585M",
    pixel_scale_arcsec=OpticalTrainProfile.compute_scale(2.9, 2030.0),
    roles=frozenset({TrainRole.DSO, TrainRole.LUNAR, TrainRole.GENERAL}),
)

C8_REDUCER_063_ATR585M = OpticalTrainProfile(
    profile_id="C8_REDUCER_063_ATR585M",
    focal_mm=1279.0,
    camera_model="ATR585M",
    pixel_scale_arcsec=OpticalTrainProfile.compute_scale(2.9, 1279.0),
    roles=frozenset({TrainRole.DSO}),
)

# ── C8 + 678M ─────────────────────────────────────────────────────────────────

C8_NATIVE_678M = OpticalTrainProfile(
    profile_id="C8_NATIVE_678M",
    focal_mm=2030.0,
    camera_model="G3M678M",
    pixel_scale_arcsec=OpticalTrainProfile.compute_scale(2.0, 2030.0),
    roles=frozenset({TrainRole.PLANETARY, TrainRole.LUNAR}),
)

C8_REDUCER_063_678M = OpticalTrainProfile(
    profile_id="C8_REDUCER_063_678M",
    focal_mm=1279.0,
    camera_model="G3M678M",
    pixel_scale_arcsec=OpticalTrainProfile.compute_scale(2.0, 1279.0),
    roles=frozenset({TrainRole.DSO, TrainRole.GENERAL}),
)

C8_BARLOW_2X_678M = OpticalTrainProfile(
    profile_id="C8_BARLOW_2X_678M",
    focal_mm=4060.0,
    camera_model="G3M678M",
    pixel_scale_arcsec=OpticalTrainProfile.compute_scale(2.0, 4060.0),
    roles=frozenset({TrainRole.PLANETARY}),
)

# ── Guide scope + IMX290 ──────────────────────────────────────────────────────

GUIDESCOPE_IMX290 = OpticalTrainProfile(
    profile_id="GUIDESCOPE_IMX290",
    focal_mm=180.0,
    camera_model="GPCMOS02000KPA",
    pixel_scale_arcsec=OpticalTrainProfile.compute_scale(2.9, 180.0),
    roles=frozenset({TrainRole.GUIDING}),
)

# ── OAG + 678M (on C8 native optical path) ───────────────────────────────────

OAG_678M = OpticalTrainProfile(
    profile_id="OAG_678M",
    focal_mm=2030.0,
    camera_model="G3M678M",
    pixel_scale_arcsec=OpticalTrainProfile.compute_scale(2.0, 2030.0),
    roles=frozenset({TrainRole.GUIDING}),
)

# ── Registry ──────────────────────────────────────────────────────────────────

ALL_TRAINS: dict[str, OpticalTrainProfile] = {
    t.profile_id: t
    for t in (
        C8_NATIVE_ATR585M,
        C8_REDUCER_063_ATR585M,
        C8_NATIVE_678M,
        C8_REDUCER_063_678M,
        C8_BARLOW_2X_678M,
        GUIDESCOPE_IMX290,
        OAG_678M,
    )
}


def get_train(profile_id: str) -> OpticalTrainProfile | None:
    """Return the OpticalTrainProfile for *profile_id*, or None if unknown."""
    return ALL_TRAINS.get(profile_id)
