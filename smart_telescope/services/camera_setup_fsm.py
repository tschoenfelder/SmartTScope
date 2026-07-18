"""Per-camera readiness FSM — M10-003: parallel to the observing FSM.

For every camera the identification scan (M10-002) reports DETECTED, a
worker claims ``camera:N`` through the JobManager and drives the camera
through its setup phases:

    IDLE → TUNING → STAR_CHECK → FOCUSING (has_focuser trains only)
         → READY | DEGRADED(reason)

Frames are fed through the external LiveAnalysis module (via the M10-004
shim) with a rolling ``previous_star_state``.  This slice records the
module's exposure/gain recommendations but does not apply them — the
clamped auto-tune loop is M10-005, and the SCT-aware coarse-focus step is
M10-006 (FOCUSING currently completes with a pending note, or runs an
injected ``focus_fn``).

A camera held by another job (autogain, a running session) simply stays
IDLE with a "camera busy" reason and is retried on the next watcher tick —
JobManager arbitration guarantees no resource conflict (M10-003 acceptance).
DEGRADED never blocks the mount flow; only automatic polar alignment will
gate on READY (M10-007).
"""
from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from enum import Enum
from typing import Any

from . import live_analysis_shim
from .job_manager import JobManager, ResourceConflictError

_log = logging.getLogger(__name__)

_WATCH_INTERVAL_S = 5.0

# M10-017: the ToupTek SDK raises bare HRESULT numbers ("-2147024726") on
# open failures — translate the ones seen in the field to plain language.
_HRESULT_BUSY = -2147024726          # 0x800700AA — ERROR_BUSY
_HRESULT_HINTS = {
    _HRESULT_BUSY: "device already in use by another process or handle",
    -2147024891: "access denied — check USB permissions/udev rules",   # 0x80070005
    -2147024865: "device not functioning — USB link problem",          # 0x8007001F
    -2147023436: "timed out waiting for the device",                   # 0x800705B4
}


def _describe_camera_error(exc: BaseException) -> str:
    text = str(exc).strip()
    try:
        code = int(text)
    except ValueError:
        return str(exc)
    hint = _HRESULT_HINTS.get(code)
    hex_code = format(code & 0xFFFFFFFF, "#010x")
    return f"{text} ({hex_code}: {hint})" if hint else f"{text} ({hex_code})"


def _is_busy_error(exc: BaseException) -> bool:
    return str(exc).strip() == str(_HRESULT_BUSY)


class CameraSetupPhase(str, Enum):
    IDLE = "IDLE"
    TUNING = "TUNING"
    STAR_CHECK = "STAR_CHECK"
    FOCUSING = "FOCUSING"
    READY = "READY"
    DEGRADED = "DEGRADED"


_ACTIVE_PHASES = {
    CameraSetupPhase.TUNING,
    CameraSetupPhase.STAR_CHECK,
    CameraSetupPhase.FOCUSING,
}
_TERMINAL_PHASES = {CameraSetupPhase.READY, CameraSetupPhase.DEGRADED}


class CameraSetupService:
    """Watches identification results and runs one setup FSM per camera."""

    def __init__(
        self,
        job_manager: JobManager,
        camera_provider: Callable[[str], Any],
        readiness_snapshot: Callable[[], dict[str, Any]],
        registry_provider: Callable[[], Any] | None = None,
        analyze_fn: Callable[..., dict[str, Any]] | None = None,
        camera_info_fn: Callable[..., dict[str, Any]] | None = None,
        focus_fn: Callable[[Any, dict[str, Any] | None], str] | None = None,
    ) -> None:
        self._job_manager = job_manager
        self._camera_provider = camera_provider
        self._readiness_snapshot = readiness_snapshot
        self._registry_provider = registry_provider
        self._analyze_fn = analyze_fn or live_analysis_shim.analyze
        self._camera_info_fn = camera_info_fn or live_analysis_shim.build_camera_info
        self._focus_fn = focus_fn
        self._lock = threading.Lock()
        self._status: dict[str, dict[str, Any]] = {}
        self._cancel_events: dict[str, threading.Event] = {}
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def start(self, poll_interval: float = _WATCH_INTERVAL_S) -> None:
        """Start the watcher loop (idempotent)."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._watch_loop, args=(poll_interval,),
            daemon=True, name="camera-setup",
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        for event in self._cancel_events.values():
            event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def poll_once(self) -> None:
        """One synchronous watcher pass (used by tests and on-demand refresh)."""
        self._launch_pending()

    # ── queries ───────────────────────────────────────────────────────────────

    def snapshot(self) -> dict[str, dict[str, Any]]:
        """Thread-safe copy of per-role setup state."""
        with self._lock:
            return {role: dict(entry) for role, entry in self._status.items()}

    # ── internals ─────────────────────────────────────────────────────────────

    def _settings(self) -> Any:
        from .. import config
        return config.LIVE_ANALYSIS

    def _watch_loop(self, interval: float) -> None:
        while not self._stop_event.is_set():
            try:
                self._launch_pending()
            except Exception as exc:  # must never kill the loop
                _log.warning("CameraSetupService: watcher pass failed: %s", exc)
            self._stop_event.wait(timeout=interval)

    def _launch_pending(self) -> None:
        if not self._settings().enabled:
            return
        readiness = self._readiness_snapshot()
        for role, entry in readiness.get("roles", {}).items():
            if entry.get("status") != "DETECTED":
                continue
            with self._lock:
                phase = self._status.get(role, {}).get("phase")
            if phase in {p.value for p in _ACTIVE_PHASES | _TERMINAL_PHASES}:
                continue
            self._launch_role(role, entry.get("sdk_index"))

    def _launch_role(self, role: str, sdk_index: int | None) -> None:
        resource = f"camera:{sdk_index}" if sdk_index is not None else f"camera:{role}"
        cancel = threading.Event()
        # Mark active BEFORE submit — the worker thread may finish (and write a
        # terminal phase) before this thread runs again.
        self._set(role, CameraSetupPhase.TUNING, reason=None)
        try:
            self._job_manager.submit(
                f"camera-setup:{role}", {resource},
                self._work, role, cancel,
                cancel_event=cancel,
            )
        except ResourceConflictError as exc:
            self._set(role, CameraSetupPhase.IDLE, reason=f"camera busy: {exc}")
            return
        self._cancel_events[role] = cancel

    def _work(self, role: str, cancel: threading.Event) -> None:
        try:
            self._run_phases(role, cancel)
        except Exception as exc:
            _log.warning("CameraSetupService: setup for %r failed: %s", role, exc)
            self._set(role, CameraSetupPhase.DEGRADED, reason=_describe_camera_error(exc))

    def _run_phases(self, role: str, cancel: threading.Event) -> None:
        settings = self._settings()
        try:
            camera = self._camera_provider(role)
        except Exception as exc:
            if _is_busy_error(exc):
                # Whoever holds the device may release it (preview page closed,
                # autogain finished) — stay IDLE so the watcher retries.
                self._set(
                    role, CameraSetupPhase.IDLE,
                    reason=f"camera busy: {_describe_camera_error(exc)}",
                )
            else:
                self._set(
                    role, CameraSetupPhase.DEGRADED,
                    reason=f"camera unavailable: {_describe_camera_error(exc)}",
                )
            return

        star_state: dict[str, Any] | None = None
        analysis: dict[str, Any] | None = None

        # TUNING — capture frames and record the module's recommendations.
        # Applying them (clamped) is M10-005; until then the recommendation is
        # surfaced in the snapshot so the card can already show it.
        self._set(role, CameraSetupPhase.TUNING, reason=None)
        for _ in range(max(1, settings.tuning_frames)):
            if cancel.is_set():
                self._set(role, CameraSetupPhase.IDLE, reason="cancelled")
                return
            analysis, star_state = self._capture_and_analyze(
                role, camera, settings.setup_exposure_s, star_state,
            )

        # STAR_CHECK — enough stars to attempt a plate solve later?
        self._set(role, CameraSetupPhase.STAR_CHECK)
        stars = self._stars_found(analysis)
        for _ in range(max(0, settings.star_check_frames)):
            if stars >= settings.star_count_min:
                break
            if cancel.is_set():
                self._set(role, CameraSetupPhase.IDLE, reason="cancelled")
                return
            analysis, star_state = self._capture_and_analyze(
                role, camera, settings.setup_exposure_s, star_state,
            )
            stars = self._stars_found(analysis)
        if stars < settings.star_count_min:
            self._set(
                role, CameraSetupPhase.DEGRADED,
                reason=f"only {stars} star(s) detected (min {settings.star_count_min})",
            )
            return

        # FOCUSING — only trains that have a focuser.
        if self._has_focuser(role):
            self._set(role, CameraSetupPhase.FOCUSING)
            if cancel.is_set():
                self._set(role, CameraSetupPhase.IDLE, reason="cancelled")
                return
            if self._focus_fn is not None:
                note = self._focus_fn(camera, analysis)
            else:
                note = "coarse focus check pending (M10-006)"
            self._set(role, CameraSetupPhase.FOCUSING, focus_note=note)

        self._set(role, CameraSetupPhase.READY, reason=None)

    def _capture_and_analyze(
        self,
        role: str,
        camera: Any,
        exposure_s: float,
        star_state: dict[str, Any] | None,
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        frame = camera.capture(exposure_s)
        camera_info = self._camera_info_fn(camera, frame=frame)
        try:
            result = self._analyze_fn(camera_info, frame, previous_star_state=star_state)
        except ImportError as exc:
            raise RuntimeError(f"LiveAnalysis module unavailable: {exc}") from exc
        single = result.get("single_frame", {})
        self._set(
            role, None,
            stars_found=single.get("stars_found"),
            image_quality=single.get("image_quality"),
            exposure_s=camera_info.get("exposure_s"),
            gain=camera_info.get("gain"),
            recommendation=result.get("recommendation"),
            frames_analyzed_inc=1,
        )
        return result, result.get("state")

    @staticmethod
    def _stars_found(analysis: dict[str, Any] | None) -> int:
        if not analysis:
            return 0
        return int(analysis.get("single_frame", {}).get("stars_found") or 0)

    def _has_focuser(self, role: str) -> bool:
        if self._registry_provider is None:
            return False
        try:
            registry = self._registry_provider()
            train = registry.by_camera_role(role) if registry is not None else None
            return bool(train is not None and train.has_focuser)
        except Exception:
            return False

    def _set(
        self,
        role: str,
        phase: CameraSetupPhase | None,
        *,
        frames_analyzed_inc: int = 0,
        **fields: Any,
    ) -> None:
        with self._lock:
            entry = self._status.setdefault(role, {
                "phase": CameraSetupPhase.IDLE.value,
                "reason": None,
                "stars_found": None,
                "image_quality": None,
                "exposure_s": None,
                "gain": None,
                "recommendation": None,
                "focus_note": None,
                "frames_analyzed": 0,
            })
            if phase is not None:
                entry["phase"] = phase.value
                if "reason" not in fields:
                    entry["reason"] = None
            entry["frames_analyzed"] += frames_analyzed_inc
            entry.update(fields)
