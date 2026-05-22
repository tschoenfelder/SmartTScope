"""Headless measure-only guide/OAG telemetry test.

This command runs guide-capable camera roles concurrently, measures centroids,
selects one active source, and emits would-be guide pulses without moving the
mount. It is intended as the first Raspberry Pi proof step before closed-loop
guiding is enabled.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

from .. import config
from ..domain.guiding import GuideFrame
from ..services.guide_measurement import (
    CentroidConfig,
    GuideCentroidEstimator,
    GuideControllerConfig,
    GuideSourceSelector,
    MeasureOnlyGuideController,
    source_state_from_measurement,
)

if TYPE_CHECKING:
    from ..ports.camera import CameraPort
    from ..services.managed_camera import ManagedCamera


@dataclass
class GuideRoleLoad:
    role: str
    exposure_s: float
    cadence_s: float


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run measure-only guide/OAG centroid telemetry without mount pulses."
    )
    parser.add_argument("--duration", type=float, default=300.0)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--primary-role", default=config.GUIDING.primary_role)
    parser.add_argument("--allow-fallback", action=argparse.BooleanOptionalAction, default=config.GUIDING.allow_fallback)
    parser.add_argument("--max-frame-age", type=float, default=config.GUIDING.max_frame_age_s)
    parser.add_argument("--roi", type=int, default=config.GUIDING.centroid_roi_px)
    parser.add_argument("--min-peak-snr", type=float, default=config.GUIDING.min_peak_snr)
    parser.add_argument(
        "--role",
        action="append",
        default=[],
        metavar="ROLE:EXPOSURE:CADENCE",
        help="Guide role, exposure seconds, cadence seconds. Repeatable.",
    )
    return parser.parse_args(argv)


def _default_roles() -> list[GuideRoleLoad]:
    roles: list[GuideRoleLoad] = []
    for role in ("guide", "oag"):
        if role in config.CAMERA_SPECS and config.CAMERA_SPECS[role].enabled:
            roles.append(GuideRoleLoad(role, 0.5, 0.5))
    return roles


def _parse_role(value: str) -> GuideRoleLoad:
    parts = value.split(":")
    if len(parts) != 3:
        raise SystemExit(f"Invalid --role {value!r}; expected ROLE:EXPOSURE:CADENCE")
    return GuideRoleLoad(parts[0], float(parts[1]), float(parts[2]))


def _build_camera(role: str) -> CameraPort:
    spec = config.CAMERA_SPECS.get(role)
    if spec is None:
        raise SystemExit(f"Camera role {role!r} is not configured in {config.CONFIG_PATH}")
    if not spec.enabled:
        raise SystemExit(f"Camera role {role!r} is disabled in {config.CONFIG_PATH}")
    if spec.backend.lower() != "native":
        raise SystemExit(f"Camera role {role!r} uses backend {spec.backend!r}; measure test is native-only for MVP")
    from ..adapters.touptek.managed import SmartTouptekCamera

    cam = SmartTouptekCamera(
        index=spec.index or 0,
        camera_id=spec.camera_id or None,
        model=spec.model or None,
        name=spec.name or None,
        capture_mode=spec.capture_mode,
        setup_profile=spec.setup_profile,
        startup_delay_s=spec.startup_delay_s,
        startup_monitor_interval_s=spec.startup_monitor_interval_s,
        prime_attempts=spec.prime_attempts,
        prime_timeout_s=spec.prime_timeout_s,
        prime_exposure_s=spec.prime_exposure_s,
        bit_depth=spec.bit_depth,
    )
    print(
        f"connecting role={role} model={spec.model or '*'} mode={spec.capture_mode} "
        f"startup_delay={spec.startup_delay_s}s",
        flush=True,
    )
    if not cam.connect():
        raise SystemExit(f"Camera role {role!r} failed to connect")
    cam.set_gain(spec.gain)
    if spec.offset_hcg or spec.offset_lcg:
        cam.set_black_level(spec.offset_for("HCG"))
    return cam


def _write_snapshot(path: Path | None, result: dict, status: str) -> None:
    if path is None:
        return
    snapshot = dict(result)
    snapshot["status"] = status
    snapshot["updated_at"] = datetime.now(timezone.utc).isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    roles = [_parse_role(item) for item in args.role] if args.role else _default_roles()
    if not roles:
        raise SystemExit("No guide roles configured. Add [cameras.guide] or [cameras.oag], or pass --role.")

    selected_specs = {
        role.role: config.CAMERA_SPECS[role.role]
        for role in roles
        if role.role in config.CAMERA_SPECS and config.CAMERA_SPECS[role.role].enabled
    }
    try:
        from ..adapters.touptek.managed import validate_unique_camera_roles
        resolved = validate_unique_camera_roles(selected_specs)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc

    from ..services.managed_camera import ManagedCamera

    estimator = GuideCentroidEstimator(
        CentroidConfig(roi_px=args.roi, min_peak_snr=args.min_peak_snr)
    )
    selector = GuideSourceSelector(primary_role=args.primary_role, allow_fallback=args.allow_fallback)
    controller = MeasureOnlyGuideController(GuideControllerConfig())
    managed: list[tuple[GuideRoleLoad, ManagedCamera]] = []
    targets: dict[str, tuple[float, float]] = {}
    bad_counts = {role.role: 0 for role in roles}
    last_sequence = {role.role: 0 for role in roles}
    latest_states = {}
    result = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "config_path": str(config.CONFIG_PATH) if config.CONFIG_PATH else "",
        "duration_s": args.duration,
        "roles": [asdict(role) for role in roles],
        "primary_role": args.primary_role,
        "allow_fallback": args.allow_fallback,
        "max_frame_age_s": args.max_frame_age,
        "resolved_cameras": resolved,
        "measurements": {role.role: [] for role in roles},
        "source_selection": [],
        "errors": {role.role: [] for role in roles},
        "dropped": {role.role: 0 for role in roles},
        "status": "starting",
    }
    _write_snapshot(args.json_out, result, "starting")

    try:
        for role in roles:
            cam = _build_camera(role.role)
            wrapper = ManagedCamera(cam, role.role)
            wrapper.start_stream(role.exposure_s, role.cadence_s)
            managed.append((role, wrapper))
            print(f"started role={role.role}", flush=True)
            _write_snapshot(args.json_out, result, "running")

        deadline = time.monotonic() + args.duration
        test_start = time.monotonic()
        next_snapshot = time.monotonic()
        while time.monotonic() < deadline:
            changed = False
            for role, wrapper in managed:
                latest = wrapper.mailbox.wait_latest(
                    after_sequence=last_sequence[role.role],
                    timeout_s=0.1,
                )
                err = wrapper.pop_stream_error()
                hard_failure = None
                if err is not None:
                    hard_failure = str(err)
                    result["errors"][role.role].append(hard_failure)
                    print(f"error role={role.role}: {err}", file=sys.stderr, flush=True)
                    changed = True
                measurement = None
                latest_frame_age = None
                if latest is not None:
                    changed = True
                    last_sequence[role.role] = latest.sequence
                    now = time.monotonic()
                    guide_frame = GuideFrame(
                        role=role.role,
                        sequence=latest.sequence,
                        captured_at_monotonic=latest.captured_at_monotonic,
                        received_at_monotonic=now,
                        exposure_s=latest.frame.exposure_seconds,
                        shape=tuple(int(v) for v in latest.frame.pixels.shape),
                        dtype=str(latest.frame.pixels.dtype),
                        dropped_before=latest.dropped_before,
                    )
                    latest_frame_age = guide_frame.frame_age_s
                    target = targets.get(role.role)
                    measurement = estimator.measure(
                        latest.frame.pixels,
                        role=role.role,
                        sequence=latest.sequence,
                        frame_age_s=latest_frame_age,
                        target=target,
                    )
                    if measurement.accepted and target is None and measurement.centroid_x is not None and measurement.centroid_y is not None:
                        targets[role.role] = (measurement.centroid_x, measurement.centroid_y)
                    if measurement.accepted and latest_frame_age <= args.max_frame_age:
                        bad_counts[role.role] = 0
                    else:
                        bad_counts[role.role] += 1
                    result["measurements"][role.role].append(
                        {
                            "elapsed_s": round(now - test_start, 3),
                            "frame": guide_frame.to_dict(),
                            "measurement": measurement.to_dict(),
                        }
                    )
                result["dropped"][role.role] = wrapper.mailbox.dropped_count
                latest_states[role.role] = source_state_from_measurement(
                    role.role,
                    measurement,
                    running=True,
                    latest_sequence=last_sequence[role.role],
                    latest_frame_age_s=latest_frame_age,
                    bad_frame_count=bad_counts[role.role],
                    fallback_after_bad_frames=config.GUIDING.fallback_after_bad_frames,
                    hard_failure=hard_failure,
                )

            active = selector.select(latest_states)
            active_measurement = latest_states.get(active).measurement if active else None
            pulses = controller.would_pulse(active_measurement) if active_measurement is not None else []
            if changed:
                result["source_selection"].append(
                    {
                        "elapsed_s": round(time.monotonic() - test_start, 3),
                        "active_role": active,
                        "reason": selector.reason,
                        "would_pulses": [pulse.to_dict() for pulse in pulses],
                        "states": {role: state.to_dict() for role, state in latest_states.items()},
                    }
                )
            now = time.monotonic()
            if changed or now >= next_snapshot:
                _write_snapshot(args.json_out, result, "running")
                next_snapshot = now + 5.0
    finally:
        for _role, wrapper in managed:
            wrapper.stop_stream()
            wrapper.camera.disconnect()

    result["finished_at"] = datetime.now(timezone.utc).isoformat()
    result["status"] = "finished"
    _write_snapshot(args.json_out, result, "finished")
    print(
        json.dumps(
            {
                "duration_s": result["duration_s"],
                "roles": result["roles"],
                "primary_role": result["primary_role"],
                "measurements": {role.role: len(result["measurements"][role.role]) for role in roles},
                "errors": {role.role: len(result["errors"][role.role]) for role in roles},
                "dropped": result["dropped"],
                "last_active_role": result["source_selection"][-1]["active_role"] if result["source_selection"] else None,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
