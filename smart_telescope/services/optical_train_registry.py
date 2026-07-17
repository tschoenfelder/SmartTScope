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
from collections.abc import Callable
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
    # M10-013: declared optical elements — what is actually in this light path.
    filter_wheel: str = ""      # "touptek" (global [filter_wheel] device) | ""
    reducer: str = ""           # descriptive label, e.g. "celestron_f6.3"
    barlow: str = ""            # descriptive label, e.g. "2x"
    # M10-015: True when pixel_scale_arcsec came from an explicit config
    # override (which then also beats a driver-reported pixel size).
    pixel_scale_overridden: bool = False

    def effective_pixel_scale(
        self, binning: int = 1, pixel_size_um: float | None = None,
    ) -> float:
        """M10-015: arcsec/px at the given binning — pixel scale is derived,
        never a required config value.

        Precedence for the binning-1 base: explicit config override >
        driver-reported ``pixel_size_um`` (pass
        ``camera.get_capabilities().pixel_size_um`` when the camera is
        connected) > model-profile derivation done at registry build.
        Binning multiplies the base (2×2 binning doubles arcsec/px).
        """
        base = self.pixel_scale_arcsec
        if (
            not self.pixel_scale_overridden
            and pixel_size_um is not None and pixel_size_um > 0
            and self.focal_mm > 0
        ):
            base = round(pixel_size_um * 206.265 / self.focal_mm, 4)
        return round(base * max(1, int(binning)), 4)

    def optical_configuration(self) -> dict[str, object]:
        """Serializable summary for API payloads (M10-002/M10-008)."""
        return {
            "telescope": self.telescope_name,
            "focuser": self.focuser or None,
            "filter_wheel": self.filter_wheel or None,
            "reducer": self.reducer or None,
            "barlow": self.barlow or None,
            "reducer_factor": self.reducer_factor,
            "focal_mm": self.focal_mm,
            "pixel_scale_arcsec": self.pixel_scale_arcsec,
        }


def _derive_pixel_scale(camera_role: str, focal_mm: float) -> float:
    """Compute pixel scale from the role's configured camera model; fall back to global.

    M10-015: the profile lookup uses the *configured model* for this role
    (``[cameras.<role>] model``). The old behavior matched profile names against
    the role name itself ("main"/"guide"/"oag") — which never matched, so every
    train silently used the global fallback. Role-name matching is kept only as
    a legacy path for configs where the role IS the model name.
    """
    from .. import config
    from ..domain.camera_profile import ALL_PROFILES

    if focal_mm <= 0:
        return config.PIXEL_SCALE_ARCSEC

    spec = config.CAMERA_SPECS.get(camera_role)
    lookup = (spec.model if spec is not None and spec.model else "") or camera_role

    for model, profile in ALL_PROFILES.items():
        if model.lower() in lookup.lower():
            scale = round(profile.pixel_um * 206.265 / focal_mm, 4)
            _log.debug(
                "pixel scale for role '%s': %.4f arcsec/px (model=%s, via %s)",
                camera_role, scale, model,
                "configured model" if lookup is not camera_role else "role name",
            )
            return scale

    _log.debug(
        "pixel scale for role '%s': no profile match for '%s' — using global %.4f arcsec/px",
        camera_role, lookup, config.PIXEL_SCALE_ARCSEC,
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
    def from_config(
        cls,
        resolve_index: "Callable[[str], int | None] | None" = None,
    ) -> OpticalTrainRegistry:
        """Build registry from config.TELESCOPES + config.OPTICAL_TRAINS + config.CAMERAS.

        Args:
            resolve_index: optional callable mapping a camera role to its real
                SDK enumeration index (M10-015 — the runtime wires a
                CameraNameResolver-backed one). ``None`` return values fall
                back to the configured/default index. Kept injectable so tests
                and SDK-less environments never touch hardware enumeration.

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

            # Resolve camera index: prefer CAMERA_SPECS (table format) then CAMERAS (legacy).
            if spec.camera in config.CAMERA_SPECS:
                raw_idx = config.CAMERA_SPECS[spec.camera].index
                camera_index: int = raw_idx if raw_idx is not None else 0
            elif spec.camera in config.CAMERAS:
                raw = config.CAMERAS[spec.camera]
                camera_index = int(raw) if isinstance(raw, (int, float)) else 0
            else:
                all_roles = list(config.CAMERA_SPECS) or list(config.CAMERAS) or ["(none)"]
                errors.append(
                    f"[optical_trains.{name}]: camera role '{spec.camera}' not found in "
                    f"[cameras] (configured roles: {all_roles})"
                )
                continue
            # M10-015: prefer the real SDK enumeration index when a resolver
            # is available (default-0-for-all made by_camera_index ambiguous).
            if resolve_index is not None:
                try:
                    resolved = resolve_index(spec.camera)
                except Exception as exc:  # resolver must never break startup
                    _log.debug("index resolution failed for role '%s': %s", spec.camera, exc)
                    resolved = None
                if resolved is not None:
                    camera_index = resolved

            focal_mm = round(tele.focal_mm * spec.reducer_factor, 2)

            pixel_scale_overridden = spec.pixel_scale_arcsec > 0.0
            if pixel_scale_overridden:
                pixel_scale = spec.pixel_scale_arcsec
            else:
                pixel_scale = _derive_pixel_scale(spec.camera, focal_mm)

            # M10-013: validate declared optical elements.
            if spec.filter_wheel not in ("", "touptek"):
                errors.append(
                    f"[optical_trains.{name}]: filter_wheel '{spec.filter_wheel}' unknown "
                    f"— supported: \"touptek\" or \"\" (none)"
                )
                continue
            if spec.filter_wheel == "touptek" and not config.FILTER_WHEEL.enabled:
                errors.append(
                    f"[optical_trains.{name}]: filter_wheel = \"touptek\" but the global "
                    f"[filter_wheel] section is not enabled — set [filter_wheel] enabled = true "
                    f"or remove the reference"
                )
                continue
            # Label/factor consistency is a warning, not an error (the factor
            # stays the numeric authority for focal/pixel-scale math).
            has_element = bool(spec.reducer or spec.barlow)
            if has_element and spec.reducer_factor == 1.0:
                _log.warning(
                    "[optical_trains.%s]: reducer/barlow declared (%s) but reducer_factor "
                    "is 1.0 — focal length math ignores the declared element",
                    name, spec.reducer or spec.barlow,
                )
            elif not has_element and spec.reducer_factor != 1.0:
                _log.warning(
                    "[optical_trains.%s]: reducer_factor %.2f set but no reducer/barlow "
                    "declared — consider naming the element for the camera card",
                    name, spec.reducer_factor,
                )

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
                filter_wheel=spec.filter_wheel,
                reducer=spec.reducer,
                barlow=spec.barlow,
                pixel_scale_overridden=pixel_scale_overridden,
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
