"""Collimation assistant configuration — Task 0.1.

All config dataclasses are frozen so they can be passed around safely.
Load from the [collimation] section of config.toml via CollimationConfig.from_dict().
Invalid values are rejected in CollimationConfig.validate().
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


# ── Enums ─────────────────────────────────────────────────────────────────────

class ReferenceCenterSource(str, Enum):
    FRAME_CENTER = "frame_center"
    CALIBRATED   = "calibrated"


class FocuserDirection(str, Enum):
    CLOCKWISE         = "clockwise"
    COUNTER_CLOCKWISE = "counter_clockwise"


class MountCenteringMethod(str, Enum):
    PULSE_GUIDE = "pulse_guide"
    GOTO        = "goto"


# ── Sub-configs ───────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ReferenceCenterConfig:
    """Where to find the optical axis reference in image coordinates.

    MVP: offset is (0, 0) — reference equals frame center.
    Later: store calibrated offset per optical-train profile.
    """
    offset_x_px: float = 0.0
    offset_y_px: float = 0.0
    source: ReferenceCenterSource = ReferenceCenterSource.FRAME_CENTER

    @classmethod
    def from_dict(cls, d: dict) -> ReferenceCenterConfig:
        return cls(
            offset_x_px=float(d.get("offset_x_px", 0.0)),
            offset_y_px=float(d.get("offset_y_px", 0.0)),
            source=ReferenceCenterSource(d.get("source", "frame_center")),
        )


@dataclass(frozen=True)
class ContradictionDetectionConfig:
    """Controls when the assistant stops issuing screw-turn commands."""
    enabled: bool = True
    stop_on_conflicting_indicators: bool = True
    require_recenter_before_next_screw_hint: bool = True
    require_refocus_before_final_fine_hint: bool = True

    @classmethod
    def from_dict(cls, d: dict) -> ContradictionDetectionConfig:
        return cls(
            enabled=bool(d.get("enabled", True)),
            stop_on_conflicting_indicators=bool(d.get("stop_on_conflicting_indicators", True)),
            require_recenter_before_next_screw_hint=bool(
                d.get("require_recenter_before_next_screw_hint", True)),
            require_refocus_before_final_fine_hint=bool(
                d.get("require_refocus_before_final_fine_hint", True)),
        )


@dataclass(frozen=True)
class DaylightAlignmentConfig:
    """Daylight / OCAL-like mechanical pre-check — disabled for MVP."""
    enabled: bool = False
    mode: str = "optional_non_mvp"
    camera_id: str = "ocal_like_collimation_camera"
    warning: str = (
        "Mechanical concentricity is only a rough pre-check; "
        "final SCT collimation requires star validation."
    )

    @classmethod
    def from_dict(cls, d: dict) -> DaylightAlignmentConfig:
        return cls(
            enabled=bool(d.get("enabled", False)),
            mode=str(d.get("mode", "optional_non_mvp")),
            camera_id=str(d.get("camera_id", "ocal_like_collimation_camera")),
            warning=str(d.get("warning", (
                "Mechanical concentricity is only a rough pre-check; "
                "final SCT collimation requires star validation."
            ))),
        )


@dataclass(frozen=True)
class FocuserCollimationConfig:
    """Focuser parameters for the collimation assistant."""
    min_position: int = 0
    max_position: int = 50000
    increasing_value_direction: FocuserDirection = FocuserDirection.CLOCKWISE
    final_approach_direction: FocuserDirection = FocuserDirection.CLOCKWISE
    defocus_direction: FocuserDirection = FocuserDirection.CLOCKWISE
    max_single_step: int = 500
    fine_step: int = 25
    coarse_step: int = 250

    @classmethod
    def from_dict(cls, d: dict) -> FocuserCollimationConfig:
        def _dir(key: str, default: str = "clockwise") -> FocuserDirection:
            return FocuserDirection(d.get(key, default))
        return cls(
            min_position=int(d.get("min_position", 0)),
            max_position=int(d.get("max_position", 50000)),
            increasing_value_direction=_dir("increasing_value_direction"),
            final_approach_direction=_dir("final_approach_direction"),
            defocus_direction=_dir("defocus_direction"),
            max_single_step=int(d.get("max_single_step", 500)),
            fine_step=int(d.get("fine_step", 25)),
            coarse_step=int(d.get("coarse_step", 250)),
        )

    def validate(self) -> None:
        if self.min_position < 0:
            raise ValueError("focuser.min_position must be >= 0")
        if self.max_position <= self.min_position:
            raise ValueError("focuser.max_position must be > min_position")
        if self.max_single_step < 1:
            raise ValueError("focuser.max_single_step must be >= 1")
        if self.fine_step < 1:
            raise ValueError("focuser.fine_step must be >= 1")
        if self.coarse_step < self.fine_step:
            raise ValueError("focuser.coarse_step must be >= fine_step")


@dataclass(frozen=True)
class MountCenteringConfig:
    """Mount centering tolerances and guide-pulse limits."""
    method: MountCenteringMethod = MountCenteringMethod.PULSE_GUIDE
    max_pulse_ms: int = 500
    settle_ms: int = 750
    initial_tolerance_px: float = 50.0
    rough_tolerance_px: float = 20.0
    fine_tolerance_px: float = 5.0

    @classmethod
    def from_dict(cls, d: dict) -> MountCenteringConfig:
        return cls(
            method=MountCenteringMethod(d.get("method", "pulse_guide")),
            max_pulse_ms=int(d.get("max_pulse_ms", 500)),
            settle_ms=int(d.get("settle_ms", 750)),
            initial_tolerance_px=float(d.get("initial_tolerance_px", 50.0)),
            rough_tolerance_px=float(d.get("rough_tolerance_px", 20.0)),
            fine_tolerance_px=float(d.get("fine_tolerance_px", 5.0)),
        )

    def validate(self) -> None:
        if self.max_pulse_ms < 1:
            raise ValueError("mount_centering.max_pulse_ms must be >= 1")
        if self.settle_ms < 0:
            raise ValueError("mount_centering.settle_ms must be >= 0")
        if not (0 < self.fine_tolerance_px
                <= self.rough_tolerance_px
                <= self.initial_tolerance_px):
            raise ValueError(
                "mount_centering tolerances must satisfy "
                "0 < fine_tolerance_px <= rough_tolerance_px <= initial_tolerance_px"
            )


@dataclass(frozen=True)
class RoughCollimationConfig:
    """Donut-based rough collimation thresholds."""
    target_donut_diameter_ratio_min: float = 0.25
    target_donut_diameter_ratio_max: float = 0.50
    good_error_ratio: float = 0.02
    fallback_error_ratio: float = 0.05

    @classmethod
    def from_dict(cls, d: dict) -> RoughCollimationConfig:
        return cls(
            target_donut_diameter_ratio_min=float(
                d.get("target_donut_diameter_ratio_min", 0.25)),
            target_donut_diameter_ratio_max=float(
                d.get("target_donut_diameter_ratio_max", 0.50)),
            good_error_ratio=float(d.get("good_error_ratio", 0.02)),
            fallback_error_ratio=float(d.get("fallback_error_ratio", 0.05)),
        )

    def validate(self) -> None:
        if not (0 < self.target_donut_diameter_ratio_min
                < self.target_donut_diameter_ratio_max < 1):
            raise ValueError(
                "rough_collimation: donut diameter ratios must satisfy "
                "0 < min < max < 1"
            )
        if not (0 < self.good_error_ratio <= self.fallback_error_ratio < 1):
            raise ValueError(
                "rough_collimation: error ratios must satisfy "
                "0 < good_error_ratio <= fallback_error_ratio < 1"
            )


@dataclass(frozen=True)
class FineCollimationConfig:
    """Tri-Bahtinov fine collimation thresholds."""
    moving_window_frames: int = 7
    target_residual_px: float = 2.0
    poor_seeing_residual_px: float = 3.0

    @classmethod
    def from_dict(cls, d: dict) -> FineCollimationConfig:
        return cls(
            moving_window_frames=int(d.get("moving_window_frames", 7)),
            target_residual_px=float(d.get("target_residual_px", 2.0)),
            poor_seeing_residual_px=float(d.get("poor_seeing_residual_px", 3.0)),
        )

    def validate(self) -> None:
        if self.moving_window_frames < 3:
            raise ValueError("fine_collimation.moving_window_frames must be >= 3")
        if self.target_residual_px <= 0:
            raise ValueError("fine_collimation.target_residual_px must be > 0")
        if self.poor_seeing_residual_px < self.target_residual_px:
            raise ValueError(
                "fine_collimation.poor_seeing_residual_px must be "
                ">= target_residual_px"
            )


# ── Top-level config ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CollimationConfig:
    """Top-level collimation assistant configuration.

    Load with CollimationConfig.from_dict(toml_cfg.get("collimation", {})).
    Call .validate() after loading to catch invalid values early.
    """
    telescope_profile: str = "c8_f10"
    camera_id: str = "main"
    mount_adapter: str = "onstep"
    focuser_adapter: str = "onstep"
    reference_center: ReferenceCenterConfig = field(
        default_factory=ReferenceCenterConfig)
    contradiction_detection: ContradictionDetectionConfig = field(
        default_factory=ContradictionDetectionConfig)
    daylight_mechanical_alignment: DaylightAlignmentConfig = field(
        default_factory=DaylightAlignmentConfig)
    focuser: FocuserCollimationConfig = field(
        default_factory=FocuserCollimationConfig)
    mount_centering: MountCenteringConfig = field(
        default_factory=MountCenteringConfig)
    rough_collimation: RoughCollimationConfig = field(
        default_factory=RoughCollimationConfig)
    fine_collimation: FineCollimationConfig = field(
        default_factory=FineCollimationConfig)

    @classmethod
    def from_dict(cls, d: dict) -> CollimationConfig:
        """Build from a TOML dict (the [collimation] section)."""
        return cls(
            telescope_profile=str(d.get("telescope_profile", "c8_f10")),
            camera_id=str(d.get("camera_id", "main")),
            mount_adapter=str(d.get("mount_adapter", "onstep")),
            focuser_adapter=str(d.get("focuser_adapter", "onstep")),
            reference_center=ReferenceCenterConfig.from_dict(
                d.get("reference_center", {})),
            contradiction_detection=ContradictionDetectionConfig.from_dict(
                d.get("contradiction_detection", {})),
            daylight_mechanical_alignment=DaylightAlignmentConfig.from_dict(
                d.get("daylight_mechanical_alignment", {})),
            focuser=FocuserCollimationConfig.from_dict(
                d.get("focuser", {})),
            mount_centering=MountCenteringConfig.from_dict(
                d.get("mount_centering", {})),
            rough_collimation=RoughCollimationConfig.from_dict(
                d.get("rough_collimation", {})),
            fine_collimation=FineCollimationConfig.from_dict(
                d.get("fine_collimation", {})),
        )

    def validate(self) -> None:
        """Raise ValueError on any invalid value.

        Called automatically by get_collimation_config() in config.py.
        """
        self.focuser.validate()
        self.mount_centering.validate()
        self.rough_collimation.validate()
        self.fine_collimation.validate()
