"""Headless multi-camera load test for Raspberry Pi deployments."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import sys
import time
from pathlib import Path

from .. import config
from ..adapters.touptek.managed import SmartTouptekCamera, validate_unique_camera_roles
from ..ports.camera import CameraPort
from ..services.managed_camera import ManagedCamera


@dataclass
class RoleLoad:
    role: str
    exposure_s: float
    cadence_s: float


@dataclass
class RoleStartup:
    role: str
    model: str
    capture_mode: str
    startup_delay_s: float
    connect_elapsed_s: float


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a no-UI concurrent camera load test."
    )
    parser.add_argument("--duration", type=float, default=300.0)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument(
        "--role",
        action="append",
        default=[],
        metavar="ROLE:EXPOSURE:CADENCE",
        help="Capture role, exposure seconds, cadence seconds. Repeatable.",
    )
    return parser.parse_args(argv)


def _default_roles() -> list[RoleLoad]:
    if ("main" in config.CAMERA_SPECS and config.CAMERA_SPECS["main"].enabled) or "main" in config.CAMERAS:
        roles = [RoleLoad("main", 30.0, 30.0)]
    else:
        roles = []
    for role in ("guide", "oag"):
        if (role in config.CAMERA_SPECS and config.CAMERA_SPECS[role].enabled) or role in config.CAMERAS:
            roles.append(RoleLoad(role, 0.5, 0.5))
    return roles


def _parse_role(value: str) -> RoleLoad:
    parts = value.split(":")
    if len(parts) != 3:
        raise SystemExit(f"Invalid --role {value!r}; expected ROLE:EXPOSURE:CADENCE")
    return RoleLoad(parts[0], float(parts[1]), float(parts[2]))


def _build_camera(role: str) -> tuple[CameraPort, RoleStartup]:
    spec = config.CAMERA_SPECS.get(role)
    if spec is None:
        configured = ", ".join(config.CAMERA_SPECS.keys() or config.CAMERAS.keys()) or "none"
        raise SystemExit(
            f"Camera role {role!r} is not configured in {config.CONFIG_PATH}. "
            f"Configured roles: {configured}"
        )
    if spec.backend.lower() != "native":
        raise SystemExit(
            f"Camera role {role!r} requests backend {spec.backend!r}. "
            "This load test is native-only for the MVP."
        )
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
    started = time.monotonic()
    if not cam.connect():
        raise SystemExit(f"Camera role {role!r} failed to connect")
    connect_elapsed_s = time.monotonic() - started
    cam.set_gain(spec.gain)
    if spec.offset_hcg or spec.offset_lcg:
        cam.set_black_level(spec.offset_for("HCG"))
    return cam, RoleStartup(
        role=role,
        model=spec.model,
        capture_mode=spec.capture_mode,
        startup_delay_s=spec.startup_delay_s,
        connect_elapsed_s=round(connect_elapsed_s, 3),
    )


def _write_snapshot(path: Path | None, result: dict, status: str) -> None:
    if path is None:
        return
    snapshot = dict(result)
    snapshot["status"] = status
    snapshot["updated_at"] = datetime.now(timezone.utc).isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")


def _summarize(result: dict) -> dict:
    summary: dict[str, dict] = {}
    for role, frames in result.get("frames", {}).items():
        errors = result.get("errors", {}).get(role, [])
        dropped = result.get("dropped", {}).get(role, 0)
        times = [float(frame["elapsed_s"]) for frame in frames]
        intervals = [round(times[i] - times[i - 1], 3) for i in range(1, len(times))]
        summary[role] = {
            "frames": len(frames),
            "errors": len(errors),
            "dropped": dropped,
            "first_frame_elapsed_s": round(times[0], 3) if times else None,
            "last_frame_elapsed_s": round(times[-1], 3) if times else None,
            "avg_interval_s": round(sum(intervals) / len(intervals), 3) if intervals else None,
            "min_interval_s": min(intervals) if intervals else None,
            "max_interval_s": max(intervals) if intervals else None,
        }
    return summary


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    roles = [_parse_role(item) for item in args.role] if args.role else _default_roles()
    if not roles:
        raise SystemExit("No camera roles configured. Add [cameras.<role>] or pass --role.")
    selected_specs = {
        role.role: config.CAMERA_SPECS[role.role]
        for role in roles
        if role.role in config.CAMERA_SPECS and config.CAMERA_SPECS[role.role].enabled
    }
    try:
        resolved = validate_unique_camera_roles(selected_specs)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc

    managed: list[tuple[RoleLoad, ManagedCamera]] = []
    result = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "config_path": str(config.CONFIG_PATH) if config.CONFIG_PATH else "",
        "duration_s": args.duration,
        "roles": [asdict(role) for role in roles],
        "startup": [],
        "resolved_cameras": resolved,
        "frames": {role.role: [] for role in roles},
        "errors": {role.role: [] for role in roles},
        "dropped": {},
        "summary": {},
        "status": "starting",
    }
    test_start = time.monotonic()
    _write_snapshot(args.json_out, result, "starting")

    try:
        for role in roles:
            cam, startup = _build_camera(role.role)
            result["startup"].append(asdict(startup))
            wrapper = ManagedCamera(cam, role.role)
            wrapper.start_stream(role.exposure_s, role.cadence_s)
            managed.append((role, wrapper))
            result["dropped"][role.role] = wrapper.mailbox.dropped_count
            result["summary"] = _summarize(result)
            _write_snapshot(args.json_out, result, "running")
            print(f"started role={role.role}", flush=True)

        deadline = time.monotonic() + args.duration
        last_sequence = {role.role: 0 for role in roles}
        next_snapshot = time.monotonic()
        while time.monotonic() < deadline:
            changed = False
            for role, wrapper in managed:
                latest = wrapper.mailbox.wait_latest(
                    after_sequence=last_sequence[role.role],
                    timeout_s=0.2,
                )
                if latest is not None:
                    last_sequence[role.role] = latest.sequence
                    changed = True
                    frame = latest.frame
                    result["frames"][role.role].append(
                        {
                            "sequence": latest.sequence,
                            "elapsed_s": round(time.monotonic() - test_start, 3),
                            "shape": list(frame.pixels.shape),
                            "exposure_s": frame.exposure_seconds,
                            "min": float(frame.pixels.min()),
                            "max": float(frame.pixels.max()),
                            "mean": float(frame.pixels.mean()),
                        }
                    )
                err = wrapper.pop_stream_error()
                if err is not None:
                    result["errors"][role.role].append(str(err))
                    changed = True
                    print(f"error role={role.role}: {err}", file=sys.stderr, flush=True)
                result["dropped"][role.role] = wrapper.mailbox.dropped_count
            now = time.monotonic()
            if changed or now >= next_snapshot:
                result["summary"] = _summarize(result)
                _write_snapshot(args.json_out, result, "running")
                next_snapshot = now + 5.0
        for role, wrapper in managed:
            result["dropped"][role.role] = wrapper.mailbox.dropped_count
    finally:
        for _role, wrapper in managed:
            wrapper.stop_stream()
            wrapper.camera.disconnect()

    result["finished_at"] = datetime.now(timezone.utc).isoformat()
    result["status"] = "finished"
    result["summary"] = _summarize(result)
    _write_snapshot(args.json_out, result, "finished")
    print(json.dumps({k: result[k] for k in ("config_path", "duration_s", "roles", "startup", "summary")}, indent=2))
    for role in roles:
        print(
            f"{role.role}: frames={len(result['frames'][role.role])} "
            f"errors={len(result['errors'][role.role])} "
            f"dropped={result['dropped'].get(role.role, 0)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
