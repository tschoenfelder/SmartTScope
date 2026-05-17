"""CoolingService — background TEC polling and temperature control.

Extracted from api/cooling.py (R6-001) so that TEC session lifecycle is owned
by a proper service rather than module-global state in an API module.
"""

from __future__ import annotations

import dataclasses
import logging
import threading
from typing import Any

from ..domain.cooling import CoolingAction, CoolingConfig, CoolingController

_log = logging.getLogger(__name__)

_POLL_INTERVAL_S = 30.0


@dataclasses.dataclass
class CoolingStatus:
    enabled: bool
    camera_index: int | None = None
    current_temp_c: float | None = None
    target_c: float | None = None
    power_pct: float = 0.0
    stable: bool = False
    action: CoolingAction | None = None
    warning_msg: str | None = None
    seconds_remaining: float = 0.0


@dataclasses.dataclass
class _Session:
    camera: Any          # CameraPort — must have TEC methods
    camera_index: int
    ctrl: CoolingController
    last_action: CoolingAction | None = None
    last_temp_c: float | None = None
    last_power_pct: float = 0.0
    warning_msg: str | None = None
    stop_event: threading.Event = dataclasses.field(default_factory=threading.Event)
    thread: threading.Thread | None = None


class CoolingService:
    """Background TEC session: poll temperature, run PID tick, apply target changes.

    Lifecycle::

        svc.start(camera, camera_index, target_c)   # begin cooling
        svc.stop()                                  # disable TEC and stop thread
        svc.get_status()                            # read current state (any time)

    Thread safety: all public methods are safe to call from any thread.
    """

    def __init__(self) -> None:
        self._session: _Session | None = None
        self._lock = threading.Lock()

    # ── public API ────────────────────────────────────────────────────────────

    def start(self, camera: Any, camera_index: int, target_c: float) -> None:
        """Start (or restart) cooling on *camera* at *target_c* degrees.

        Stops any existing session first.  Applies initial TEC settings to the
        camera before starting the background poll thread.
        """
        cfg = CoolingConfig(target_c=target_c)

        with self._lock:
            if self._session is not None:
                self._stop_session(self._session)
            ctrl = CoolingController(cfg)
            session = _Session(camera=camera, camera_index=camera_index, ctrl=ctrl)
            session.thread = threading.Thread(
                target=self._poll_loop, args=(session,),
                daemon=True, name="cooling-poll",
            )
            self._session = session

        # Apply initial TEC settings outside the lock so the lock is not held
        # while doing I/O.
        try:
            camera.set_tec_target_c(cfg.target_c)
            camera.set_tec_enabled(True)
        except Exception as exc:
            _log.warning("Cooling: initial TEC setup failed: %s", exc)

        session.thread.start()
        _log.info("Cooling enabled: camera_index=%d target=%.1f°C", camera_index, cfg.target_c)

    def stop(self) -> None:
        """Stop the current cooling session and disable the TEC."""
        with self._lock:
            if self._session is not None:
                self._stop_session(self._session)
        _log.info("Cooling disabled")

    def get_status(self) -> CoolingStatus:
        """Return a snapshot of the current cooling state."""
        with self._lock:
            s = self._session

        if s is None:
            return CoolingStatus(enabled=False)

        action = s.last_action
        return CoolingStatus(
            enabled=True,
            camera_index=s.camera_index,
            current_temp_c=s.last_temp_c,
            target_c=s.ctrl.current_target_c,
            power_pct=round(s.last_power_pct, 1),
            stable=action == CoolingAction.STABLE,
            action=action,
            warning_msg=s.warning_msg,
            seconds_remaining=round(s.ctrl.seconds_remaining, 0),
        )

    # ── internal ──────────────────────────────────────────────────────────────

    def _stop_session(self, s: _Session) -> None:
        """Stop *s*.  Caller MUST hold self._lock.

        Releases the lock while joining the poll thread (to prevent deadlock
        since the poll thread acquires self._lock in _poll_once), then
        reacquires before returning.
        """
        s.stop_event.set()
        self._lock.release()
        try:
            if s.thread is not None:
                s.thread.join(timeout=5.0)
        finally:
            self._lock.acquire()
        try:
            s.camera.set_tec_enabled(False)
        except Exception:
            pass
        self._session = None

    def _poll_loop(self, session: _Session) -> None:
        self._poll_once(session)
        while not session.stop_event.wait(timeout=_POLL_INTERVAL_S):
            self._poll_once(session)

    def _poll_once(self, session: _Session) -> None:
        camera = session.camera

        temp_c: float | None = None
        try:
            temp_c = camera.get_temperature()
        except Exception:
            pass

        power_pct: float = 0.0
        try:
            power_pct = camera.get_tec_power_pct()
        except Exception:
            pass

        if temp_c is None:
            _log.debug("Cooling poll: temperature unavailable, skipping tick")
            with self._lock:
                session.last_temp_c = None
                session.last_power_pct = power_pct
            return

        action = session.ctrl.tick(temp_c, power_pct)

        warning_msg: str | None = None
        if action == CoolingAction.RAISE_TARGET:
            new_target = session.ctrl.current_target_c
            warning_msg = f"TEC power too high — target relaxed to {new_target:.1f} °C"
            _log.warning("Cooling: %s", warning_msg)
            try:
                camera.set_tec_target_c(new_target)
            except Exception as exc:
                _log.warning("Cooling: set_tec_target_c(%.1f) failed: %s", new_target, exc)
        elif action == CoolingAction.WARN:
            warning_msg = f"TEC power {power_pct:.0f}% — above warning threshold"

        _log.info(
            "Cooling poll: camera_index=%d temp=%.1f°C target=%.1f°C power=%.0f%% action=%s",
            session.camera_index, temp_c, session.ctrl.current_target_c, power_pct, action.name,
        )

        with self._lock:
            session.last_temp_c = temp_c
            session.last_power_pct = power_pct
            session.last_action = action
            if action in (CoolingAction.RAISE_TARGET, CoolingAction.WARN):
                session.warning_msg = warning_msg
            elif action == CoolingAction.STABLE:
                session.warning_msg = None
