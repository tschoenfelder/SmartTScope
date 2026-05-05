"""Known camera profiles — static sensor characteristics for auto-gain decisions.

Unity gain values represent the point where read-noise contribution equals one ADU,
which is the recommended starting gain for DSO acquisition in each conversion-gain mode.
Sources: Sony IMX585/IMX678/IMX290 datasheets and community testing.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CameraProfile:
    model: str
    sensor: str
    width_px: int
    height_px: int
    pixel_um: float
    max_gain: int
    unity_gain_hcg: int | None
    unity_gain_lcg: int | None
    unity_gain_hdr: int | None
    min_preview_exp_ms: float
    max_preview_exp_ms: float
    supports_cooling: bool


# ── Profiles ──────────────────────────────────────────────────────────────────

# ATR585M / ATR3CMOS08300KMA — Sony IMX585, cooled, HCG + LCG + HDR, 12-bit
ATR585M = CameraProfile(
    model="ATR585M",
    sensor="IMX585",
    width_px=3840,
    height_px=2160,
    pixel_um=2.9,
    max_gain=3200,
    unity_gain_hcg=316,
    unity_gain_lcg=200,
    unity_gain_hdr=100,
    min_preview_exp_ms=0.5,
    max_preview_exp_ms=4000.0,
    supports_cooling=True,
)

# G3M678M / 678M — Sony IMX678, passive cooling, HCG + LCG, 12-bit
G3M678M = CameraProfile(
    model="G3M678M",
    sensor="IMX678",
    width_px=3840,
    height_px=2160,
    pixel_um=2.0,
    max_gain=3200,
    unity_gain_hcg=300,
    unity_gain_lcg=200,
    unity_gain_hdr=None,
    min_preview_exp_ms=0.5,
    max_preview_exp_ms=4000.0,
    supports_cooling=False,
)

# GPCMOS02000KPA — Sony IMX290, guide-scope camera, no CG, 12-bit
GPCMOS02000KPA = CameraProfile(
    model="GPCMOS02000KPA",
    sensor="IMX290",
    width_px=1920,
    height_px=1080,
    pixel_um=2.9,
    max_gain=3200,
    unity_gain_hcg=None,
    unity_gain_lcg=None,
    unity_gain_hdr=None,
    min_preview_exp_ms=0.1,
    max_preview_exp_ms=2000.0,
    supports_cooling=False,
)

# All known profiles indexed by model name
ALL_PROFILES: dict[str, CameraProfile] = {
    p.model: p for p in (ATR585M, G3M678M, GPCMOS02000KPA)
}


def get_profile(model: str) -> CameraProfile | None:
    """Return the CameraProfile for *model*, or None if unknown."""
    return ALL_PROFILES.get(model)
