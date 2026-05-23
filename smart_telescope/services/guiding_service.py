"""GuidingService — owns guide camera streams and runs the measurement loop."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..domain.guiding import GuideMeasurement, GuideSourceState, WouldGuidePulse
from .guide_measurement import (
    CentroidConfig,
    GuideCentroidEstimator,
    GuideControllerConfig,
    GuideSourceSelector,
    MeasureOnlyGuideController,
    source_state_from_measurement,
)
from .managed_camera import ManagedCamera

if TYPE_CHECKING:
    from ..ports.camera import CameraPort
    from ..ports.mount import MountPort

_log = logging.getLogger(__name__)


@dataclass
class GuidingStatus:
    state: str = "idle"  # idle | running | failed
    active_role: str | None = None
    fallback_reason: str | None = None
    sources: dict[str, GuideSourceState] = field(default_factory=dict)
    latest_pulses: list[WouldGuidePulse] = field(default_factory=list)
    started_at: float | None = None
    measure_only: bool = True

    def to_dict(self) -> dict:
        return {
            "state": self.state,
            "active_role": self.active_role,
            "fallback_reason": self.fallback_reason,
            "sources": {r: s.to_dict() for r, s in self.sources.items()},
            "latest_pulses": [p.to_dict() for p in self.latest_pulses],
            "started_at": self.started_at,
            "measure_only": self.measure_only,
        }


class GuidingService:
    """Owns ManagedCamera streams for guide/OAG roles and runs the centroid loop.

    In measure_only mode (default) pulses are computed but not sent to the mount.
    Set measure_only=False and pass a real mount to enable closed-loop corrections.
    """

    @classmethod
    def from_config(
        cls,
        *,
        primary_role: str,
        allow_fallback: bool,
        fallback_after_bad_frames: int,
        max_frame_age_s: float,
        centroid_config: CentroidConfig,
        controller_config: GuideControllerConfig,
        measure_only: bool = True,
    ) -> "GuidingService":
        return cls(
            primary_role=primary_role,
            allow_fallback=allow_fallback,
            fallback_after_bad_frames=fallback_after_bad_frames,
            max_frame_age_s=max_frame_age_s,
            estimator=GuideCentroidEstimator(centroid_config),
            selector=GuideSourceSelector(primary_role, allow_fallback),
            controller=MeasureOnlyGuideController(controller_config),
            measure_only=measure_only,
        )

    def __init__(
        self,
        *,
        primary_role: str,
        allow_fallback: bool,
        fallback_after_bad_frames: int,
        max_frame_age_s: float,
        estimator: GuideCentroidEstimator,
        selector: GuideSourceSelector,
        controller: MeasureOnlyGuideController,
        measure_only: bool = True,
    ) -> None:
        self._primary_role = primary_role
        self._allow_fallback = allow_fallback
        self._fallback_after_bad_frames = fallback_after_bad_frames
        self._max_frame_age_s = max_frame_age_s
        self._estimator = estimator
        self._selector = selector
        self._controller = controller
        self._measure_only = measure_only

        self._managed: dict[str, ManagedCamera] = {}
        self._mount: MountPort | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lifecycle_lock = threading.Lock()
        self._status_lock = threading.Lock()
        self._status = GuidingStatus(measure_only=measure_only)

    def start(
        self,
        role_cameras: dict[str, "CameraPort"],
        exposure_s: float = 0.5,
        cadence_s: float = 0.5,
        mount: "MountPort | None" = None,
    ) -> None:
        with self._lifecycle_lock:
            with self._status_lock:
                if self._status.state == "running":
                    return

            self._mount = mount
            self._stop_event.clear()
            for role, cam in role_cameras.items():
                mc = ManagedCamera(cam, role)
                mc.start_stream(exposure_s, cadence_s)
                self._managed[role] = mc

            started_at = time.monotonic()
            self._thread = threading.Thread(
                target=self._loop, args=(started_at,), daemon=True, name="guiding-loop"
            )
            self._thread.start()

            with self._status_lock:
                self._status = GuidingStatus(
                    state="running",
                    measure_only=self._measure_only,
                    started_at=started_at,
                )
        _log.info(
            "GuidingService started roles=%s measure_only=%s",
            list(role_cameras),
            self._measure_only,
        )

    def stop(self) -> None:
        self._stop_event.set()
        for mc in self._managed.values():
            mc.stop_stream()
        if self._thread is not None:
            self._thread.join(timeout=10.0)
            self._thread = None
        self._managed.clear()
        with self._status_lock:
            self._status = GuidingStatus(measure_only=self._measure_only)
        _log.info("GuidingService stopped")

    def status(self) -> GuidingStatus:
        with self._status_lock:
            return self._status

    def _loop(self, started_at: float) -> None:
        last_sequence: dict[str, int] = {role: 0 for role in self._managed}
        targets: dict[str, tuple[float, float]] = {}
        bad_counts: dict[str, int] = {role: 0 for role in self._managed}

        while not self._stop_event.is_set():
            states: dict[str, GuideSourceState] = {}

            for role, mc in list(self._managed.items()):
                latest = mc.mailbox.wait_latest(
                    after_sequence=last_sequence[role], timeout_s=0.1
                )
                hard_failure: str | None = None
                err = mc.pop_stream_error()
                if err is not None:
                    hard_failure = str(err)
                    _log.warning("guide stream error role=%s: %s", role, err)

                measurement: GuideMeasurement | None = None
                latest_frame_age: float | None = None

                if latest is None:
                    bad_counts[role] += 1
                else:
                    last_sequence[role] = latest.sequence
                    frame_age = time.monotonic() - latest.captured_at_monotonic
                    latest_frame_age = frame_age
                    target = targets.get(role)
                    try:
                        measurement = self._estimator.measure(
                            latest.frame.pixels,
                            role=role,
                            sequence=latest.sequence,
                            frame_age_s=frame_age,
                            target=target,
                        )
                    except Exception as exc:
                        _log.warning("centroid error role=%s seq=%s: %s", role, latest.sequence, exc)
                        bad_counts[role] += 1
                    else:
                        if (
                            measurement.accepted
                            and target is None
                            and measurement.centroid_x is not None
                            and measurement.centroid_y is not None
                        ):
                            targets[role] = (measurement.centroid_x, measurement.centroid_y)
                        if measurement.accepted and frame_age <= self._max_frame_age_s:
                            bad_counts[role] = 0
                        else:
                            bad_counts[role] += 1

                states[role] = source_state_from_measurement(
                    role,
                    measurement,
                    running=True,
                    latest_sequence=last_sequence[role],
                    latest_frame_age_s=latest_frame_age,
                    bad_frame_count=bad_counts[role],
                    fallback_after_bad_frames=self._fallback_after_bad_frames,
                    hard_failure=hard_failure,
                )

            active_role = self._selector.select(states)
            active_measurement = (
                states[active_role].measurement
                if active_role and active_role in states
                else None
            )
            pulses = (
                self._controller.would_pulse(active_measurement)
                if active_measurement
                else []
            )

            if not self._measure_only and pulses and self._mount is not None:
                for pulse in pulses:
                    try:
                        self._mount.guide(pulse.direction, pulse.duration_ms)
                    except Exception as exc:
                        _log.error("mount.guide failed: %s", exc)

            with self._status_lock:
                self._status = GuidingStatus(
                    state="running",
                    measure_only=self._measure_only,
                    active_role=active_role,
                    fallback_reason=self._selector.reason,
                    sources=states,
                    latest_pulses=pulses,
                    started_at=started_at,
                )
