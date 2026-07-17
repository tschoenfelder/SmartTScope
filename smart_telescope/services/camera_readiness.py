"""CameraReadinessService — M10-002: identify configured cameras in parallel.

Runs alongside the mount flow from app startup (the user is typically still
confirming time/location): a background thread enumerates connected ToupTek
devices and matches them against the configured `[cameras.*]` roles, joining
each detected camera with its optical train's full configuration (M10-013).
Never blocks the mount flow and never raises to callers.

This is the identification slice of the M10 camera-readiness track. The
per-camera readiness FSM (exposure tuning, star check, coarse focus —
M10-003..006) builds on top of these results later.

Matching is by model name only (no serial verification here): serial checks
require opening each device, which must not happen every scan while cameras
are in active use. Serial-verified resolution stays where it always was — in
the adapter build path (`CameraNameResolver` via runtime._build_adapters).
"""
from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Any

from .camera_name_resolver import CameraNameResolver

_log = logging.getLogger(__name__)

_POLL_INTERVAL_S = 15.0

# ToupTek filter wheels enumerate alongside cameras (observed on hardware
# 2026-07-17: displayname "FILTERWHEEL"). Recognize them so they are reported
# as the configured wheel, not as an unconfigured camera.
_FILTER_WHEEL_MARKERS = ("FILTERWHEEL", "FILTER WHEEL", "CFW")


def _is_filter_wheel(display_name: str) -> bool:
    upper = display_name.upper()
    return any(marker in upper for marker in _FILTER_WHEEL_MARKERS)


class CameraReadinessService:
    """Background camera identification with a thread-safe snapshot API."""

    def __init__(
        self,
        enumerate_fn: Callable[[], list[Any]] | None = None,
        registry_provider: Callable[[], Any] | None = None,
    ) -> None:
        self._enumerate_fn = enumerate_fn or CameraNameResolver()._enumerate
        self._registry_provider = registry_provider
        self._resolver = CameraNameResolver()
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._cameras: dict[str, dict[str, Any]] = {}
        self._unassigned: list[str] = []
        self._filter_wheel: dict[str, Any] | None = None
        self._sdk_available: bool = False
        self._last_scan_at: float | None = None

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def start(self, poll_interval: float = _POLL_INTERVAL_S) -> None:
        """Start the background scan loop (idempotent)."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop, args=(poll_interval,),
            daemon=True, name="camera-readiness",
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def scan_now(self) -> None:
        """Run one synchronous scan (used by tests and on-demand refresh)."""
        self._scan_once()

    # ── queries ───────────────────────────────────────────────────────────────

    def snapshot(self) -> dict[str, Any]:
        """Thread-safe copy of the latest identification state."""
        with self._lock:
            return {
                "sdk_available": self._sdk_available,
                "scanned": self._last_scan_at is not None,
                "roles": {role: dict(entry) for role, entry in self._cameras.items()},
                "unassigned": list(self._unassigned),
                "filter_wheel": dict(self._filter_wheel) if self._filter_wheel else None,
            }

    # ── internals ─────────────────────────────────────────────────────────────

    def _loop(self, interval: float) -> None:
        while not self._stop_event.is_set():
            try:
                self._scan_once()
            except Exception as exc:  # must never kill the loop
                _log.warning("CameraReadinessService: scan failed: %s", exc)
            self._stop_event.wait(timeout=interval)

    def _scan_once(self) -> None:
        from .. import config

        try:
            devices = list(self._enumerate_fn())
            sdk_available = True
        except Exception as exc:
            _log.debug("CameraReadinessService: enumeration unavailable: %s", exc)
            devices, sdk_available = [], False

        registry = None
        if self._registry_provider is not None:
            try:
                registry = self._registry_provider()
            except Exception:
                registry = None

        cameras: dict[str, dict[str, Any]] = {}
        matched_indices: set[int] = set()

        # Split filter-wheel devices out before role matching — they are not
        # cameras and must not appear as "connected but not configured".
        wheel_names = [
            str(dev.displayname)
            for dev in devices
            if _is_filter_wheel(str(dev.displayname))
        ]
        camera_devices = [
            (i, dev) for i, dev in enumerate(devices)
            if not _is_filter_wheel(str(dev.displayname))
        ]
        filter_wheel: dict[str, Any] | None = None
        if config.FILTER_WHEEL.enabled or wheel_names:
            filter_wheel = {
                "configured": config.FILTER_WHEEL.enabled,
                "detected": bool(wheel_names),
                "display_name": wheel_names[0] if wheel_names else None,
            }

        for role, spec in config.CAMERA_SPECS.items():
            entry: dict[str, Any] = {
                "role": role,
                "model": spec.model,
                "enabled": spec.enabled,
                "status": "MISSING",
                "sdk_index": None,
                "display_name": None,
                "reason": None,
                "optical": None,
            }
            if registry is not None:
                train = registry.by_camera_role(role)
                if train is not None:
                    entry["optical"] = train.optical_configuration()

            if not spec.enabled:
                entry["status"] = "DISABLED"
                entry["reason"] = "disabled in config"
            elif not devices:
                entry["reason"] = (
                    "no cameras enumerated" if sdk_available else "ToupTek SDK unavailable"
                )
            else:
                target: str | int | None = (
                    spec.index if spec.index is not None
                    else (spec.model or config.CAMERAS.get(role))
                )
                if target is None:
                    entry["reason"] = "no model/index configured for this role"
                else:
                    try:
                        # Model-only matching — empty serial map on purpose,
                        # see module docstring.
                        idx = self._resolver.resolve(target, {}, devices=devices)
                        entry["status"] = "DETECTED"
                        entry["sdk_index"] = idx
                        entry["display_name"] = str(devices[idx].displayname)
                        matched_indices.add(idx)
                    except Exception as exc:
                        entry["reason"] = str(exc)
            cameras[role] = entry

        unassigned = [
            str(dev.displayname)
            for i, dev in camera_devices
            if i not in matched_indices
        ]

        with self._lock:
            self._cameras = cameras
            self._unassigned = unassigned
            self._filter_wheel = filter_wheel
            self._sdk_available = sdk_available
            self._last_scan_at = time.monotonic()

        detected = [r for r, e in cameras.items() if e["status"] == "DETECTED"]
        missing = [r for r, e in cameras.items() if e["status"] == "MISSING"]
        _log.debug(
            "CameraReadinessService: scan done — detected=%s missing=%s unassigned=%d",
            detected, missing, len(unassigned),
        )
