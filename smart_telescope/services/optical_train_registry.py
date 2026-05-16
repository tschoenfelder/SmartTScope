"""OpticalTrainRegistry — runtime view of all configured imaging paths.

Built from [telescopes] + [optical_trains] + [cameras] in config.toml.
Validates at build time; raises ValueError on misconfiguration.

Pixel scale priority:
  1. Explicit pixel_scale_arcsec in train config  (> 0)
  2. Computed from effective focal_mm + camera sensor pixel_um (from domain profiles)
  3. Global PIXEL_SCALE_ARCSEC fallback
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class OpticalTrain:
    """One complete imaging path known to the runtime."""
    name: str                   # "main" | "guide" | "oag" | custom
    camera_role: str            # key in config.CAMERAS
    camera_index: int           # SDK index from config.CAMERAS[camera_role]
    telescope_name: str         # key in config.TELESCOPES
    focal_mm: float             # effective = telescope.focal_mm × reducer_factor
    reducer_factor: float
    pixel_scale_arcsec: float
    has_focuser: bool
    focuser: str                # "onstep" | ""


def _derive_pixel_scale(camera_role: str, focal_mm: float) -> float:
    """Try to compute pixel scale from camera model pixel size; fall back to global."""
    from .. import config
    from ..domain.camera_profile import ALL_PROFILES

    # Look for a profile whose model name appears in the camera role name (best-effort)
    for model, profile in ALL_PROFILES.items():
        if model.lower() in camera_role.lower():
            scale = round(profile.pixel_um * 206.265 / focal_mm, 4)
            _log.debug("pixel scale for role '%s': %.4f arcsec/px (model=%s)", camera_role, scale, model)
            return scale

    _log.debug(
        "pixel scale for role '%s': no profile match — using global %.4f arcsec/px",
        camera_role, config.PIXEL_SCALE_ARCSEC,
    )
    return config.PIXEL_SCALE_ARCSEC


class OpticalTrainRegistry:
    """Validated, queryable collection of optical trains for this installation."""

    def __init__(self, trains: dict[str, OpticalTrain]) -> None:
        self._trains = trains

    # ── queries ───────────────────────────────────────────────────────────────

    def get(self, name: str) -> OpticalTrain | None:
        return self._trains.get(name)

    def main(self) -> OpticalTrain | None:
        return self._trains.get("main")

    def guide(self) -> OpticalTrain | None:
        return self._trains.get("guide")

    def all(self) -> list[OpticalTrain]:
        return list(self._trains.values())

    def by_camera_index(self, idx: int) -> OpticalTrain | None:
        for t in self._trains.values():
            if t.camera_index == idx:
                return t
        return None

    def by_camera_role(self, role: str) -> OpticalTrain | None:
        for t in self._trains.values():
            if t.camera_role == role:
                return t
        return None

    # ── factory ───────────────────────────────────────────────────────────────

    @classmethod
    def from_config(cls) -> OpticalTrainRegistry:
        """Build registry from config.TELESCOPES + config.OPTICAL_TRAINS + config.CAMERAS.

        Raises ValueError listing all validation errors if the config is invalid.
        """
        from .. import config

        trains: dict[str, OpticalTrain] = {}
        errors: list[str] = []

        for name, spec in config.OPTICAL_TRAINS.items():
            tele = config.TELESCOPES.get(spec.telescope)
            if tele is None:
                errors.append(
                    f"[optical_trains.{name}]: telescope '{spec.telescope}' not defined in [telescopes]"
                )
                continue

            if spec.camera not in config.CAMERAS:
                errors.append(
                    f"[optical_trains.{name}]: camera role '{spec.camera}' not in [cameras] "
                    f"(configured roles: {list(config.CAMERAS.keys()) or ['(none)']})"
                )
                continue

            camera_index = config.CAMERAS[spec.camera]
            focal_mm = round(tele.focal_mm * spec.reducer_factor, 2)

            if spec.pixel_scale_arcsec > 0.0:
                pixel_scale = spec.pixel_scale_arcsec
            else:
                pixel_scale = _derive_pixel_scale(spec.camera, focal_mm)

            trains[name] = OpticalTrain(
                name=name,
                camera_role=spec.camera,
                camera_index=camera_index,
                telescope_name=spec.telescope,
                focal_mm=focal_mm,
                reducer_factor=spec.reducer_factor,
                pixel_scale_arcsec=pixel_scale,
                has_focuser=bool(spec.focuser),
                focuser=spec.focuser,
            )

        if errors:
            raise ValueError(
                "Optical train configuration errors:\n"
                + "\n".join(f"  • {e}" for e in errors)
            )

        _log.info(
            "OpticalTrainRegistry: %d train(s) loaded — %s",
            len(trains), list(trains.keys()) or ["(none)"],
        )
        return cls(trains)
