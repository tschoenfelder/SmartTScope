"""Guide-camera periodic monitoring service (FR-GUIDE-002).

Every check_interval_s the monitor captures one frame, analyses it with
HistogramStats, and applies a small bounded adjustment if the guide-star
peak signal has drifted outside the hysteresis band.

Status values:
  GUIDE_GAIN_OK   – signal within ±hysteresis_pct of target; no action taken
  STAR_WEAK       – signal too low but gain/exposure already at ceiling
  STAR_SATURATED  – signal too high but gain/exposure already at floor
  ADJUSTED        – settings were changed this cycle
  DAWN_WARNING    – sky background has risen > dawn_threshold_pct from baseline
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import numpy as np

from ..ports.camera import CameraPort
from .camera_profile import CameraProfile
from .histogram import HistogramStats, analyze as _analyze

_log = logging.getLogger(__name__)

# Guide-star peak target and min gain (must match autogain_service)
_GUIDE_TARGET = 0.45
_GAIN_MIN     = 100


# ── Public types ──────────────────────────────────────────────────────────────

class GuideMonitorStatus(str, Enum):
    GUIDE_GAIN_OK  = "GUIDE_GAIN_OK"
    STAR_WEAK      = "STAR_WEAK"
    STAR_SATURATED = "STAR_SATURATED"
    ADJUSTED       = "ADJUSTED"
    DAWN_WARNING   = "DAWN_WARNING"


@dataclass(frozen=True)
class GuideMonitorConfig:
    check_interval_s: float = 300.0   # 5-minute default (FR-GUIDE-002)
    max_gain_step_pct: float = 10.0   # max ±10 % gain adjustment per cycle
    max_exp_step_pct: float = 20.0    # max ±20 % exposure adjustment per cycle
    hysteresis_pct: float = 15.0      # no change if within ±15 % of target
    dawn_threshold_pct: float = 20.0  # background rise > 20 % → dawn warning


@dataclass
class GuideMonitorResult:
    status: GuideMonitorStatus
    exposure_ms: float
    gain: int
    max_frac: float
    checked_at: str                  # ISO-8601 UTC
    warning_msg: str | None = None
    dawn_warning: bool = False


# ── Service ───────────────────────────────────────────────────────────────────

class GuideMonitor:
    """Background guide-star monitoring loop.

    Call :meth:`start` to launch a daemon thread that wakes every
    *config.check_interval_s* seconds, captures a frame, and applies a
    bounded adjustment if the guide-star peak has drifted.
    """

    def __init__(
        self,
        camera: CameraPort,
        profile: CameraProfile,
        config: GuideMonitorConfig | None = None,
    ) -> None:
        self._camera  = camera
        self._profile = profile
        self._config  = config or GuideMonitorConfig()
        self._stop    = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock    = threading.Lock()
        self._result: GuideMonitorResult | None = None
        self._initial_p50: float | None = None
        # Current settings — initialised from camera when loop starts
        self._cur_exp_ms: float = 0.0
        self._cur_gain: int     = _GAIN_MIN

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Launch the background monitoring thread (no-op if already running)."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._initial_p50 = None
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="guide-monitor",
        )
        self._thread.start()
        _log.info("GuideMonitor started (interval=%.0f s)", self._config.check_interval_s)

    def stop(self) -> None:
        """Signal the monitoring thread to exit and wait for it."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None
        _log.info("GuideMonitor stopped")

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def last_result(self) -> GuideMonitorResult | None:
        with self._lock:
            return self._result

    # ── Internal loop ─────────────────────────────────────────────────────────

    def _run_loop(self) -> None:
        # Read current settings from camera
        try:
            self._cur_exp_ms = self._camera.get_exposure_ms()
            self._cur_gain   = self._camera.get_gain()
        except Exception:
            self._cur_exp_ms = self._profile.min_preview_exp_ms
            self._cur_gain   = _GAIN_MIN

        while not self._stop.is_set():
            result = self._check_once()
            with self._lock:
                self._result = result
            _log.info(
                "GuideMonitor check: status=%s exp=%.0f ms gain=%d max_frac=%.3f%s",
                result.status,
                result.exposure_ms,
                result.gain,
                result.max_frac,
                " [DAWN]" if result.dawn_warning else "",
            )
            self._stop.wait(timeout=self._config.check_interval_s)

    def _check_once(self) -> GuideMonitorResult:
        cfg = self._config
        try:
            self._camera.set_exposure_ms(self._cur_exp_ms)
            self._camera.set_gain(self._cur_gain)
            frame = self._camera.capture(self._cur_exp_ms / 1000.0)
        except Exception as exc:
            _log.error("GuideMonitor: capture failed: %s", exc)
            return GuideMonitorResult(
                status=GuideMonitorStatus.STAR_WEAK,
                exposure_ms=self._cur_exp_ms,
                gain=self._cur_gain,
                max_frac=0.0,
                checked_at=_utc_now(),
                warning_msg=str(exc),
            )

        bit_depth = 16
        try:
            bit_depth = self._camera.get_bit_depth()
        except Exception:
            pass

        stats = _analyze(frame.pixels, bit_depth=bit_depth)
        # max_frac (frame maximum), not p99_9 — a whole-frame percentile can't
        # see a sparse guide star at real sensor resolution (M10-050, same
        # root cause as M10-043/M10-049).
        signal = stats.max_frac

        # Dawn detection: persistent rise in sky background (p50)
        dawn_warning = False
        if self._initial_p50 is None:
            self._initial_p50 = stats.p50
        elif stats.p50 > self._initial_p50 * (1.0 + cfg.dawn_threshold_pct / 100.0):
            dawn_warning = True

        # Hysteresis band
        lo = _GUIDE_TARGET * (1.0 - cfg.hysteresis_pct / 100.0)
        hi = _GUIDE_TARGET * (1.0 + cfg.hysteresis_pct / 100.0)

        if lo <= signal <= hi:
            return GuideMonitorResult(
                status=GuideMonitorStatus.GUIDE_GAIN_OK if not dawn_warning
                       else GuideMonitorStatus.DAWN_WARNING,
                exposure_ms=self._cur_exp_ms,
                gain=self._cur_gain,
                max_frac=signal,
                checked_at=_utc_now(),
                dawn_warning=dawn_warning,
                warning_msg="Sky brightening — consider ending session" if dawn_warning else None,
            )

        adjusted = False
        exp_min  = self._profile.min_preview_exp_ms
        exp_max  = self._profile.max_preview_exp_ms
        gain_max = self._profile.max_gain

        if signal < lo:
            # Too weak — brighten
            if self._cur_exp_ms < exp_max - 0.1:
                new_exp = min(exp_max, self._cur_exp_ms * (1.0 + cfg.max_exp_step_pct / 100.0))
                _log.info("GuideMonitor: exp %.0f → %.0f ms (star weak)", self._cur_exp_ms, new_exp)
                self._cur_exp_ms = new_exp
                adjusted = True
            elif self._cur_gain < gain_max:
                new_gain = min(gain_max, int(self._cur_gain * (1.0 + cfg.max_gain_step_pct / 100.0)))
                _log.info("GuideMonitor: gain %d → %d (star weak)", self._cur_gain, new_gain)
                self._cur_gain = new_gain
                adjusted = True
            else:
                return GuideMonitorResult(
                    status=GuideMonitorStatus.STAR_WEAK,
                    exposure_ms=self._cur_exp_ms,
                    gain=self._cur_gain,
                    max_frac=signal,
                    checked_at=_utc_now(),
                    dawn_warning=dawn_warning,
                    warning_msg="Guide star too faint; gain and exposure at maximum",
                )
        else:
            # Too bright — dim
            if self._cur_exp_ms > exp_min + 0.001:
                new_exp = max(exp_min, self._cur_exp_ms * (1.0 - cfg.max_exp_step_pct / 100.0))
                _log.info("GuideMonitor: exp %.0f → %.0f ms (star bright)", self._cur_exp_ms, new_exp)
                self._cur_exp_ms = new_exp
                adjusted = True
            elif self._cur_gain > _GAIN_MIN:
                new_gain = max(_GAIN_MIN, int(self._cur_gain * (1.0 - cfg.max_gain_step_pct / 100.0)))
                _log.info("GuideMonitor: gain %d → %d (star bright)", self._cur_gain, new_gain)
                self._cur_gain = new_gain
                adjusted = True
            else:
                return GuideMonitorResult(
                    status=GuideMonitorStatus.STAR_SATURATED,
                    exposure_ms=self._cur_exp_ms,
                    gain=self._cur_gain,
                    max_frac=signal,
                    checked_at=_utc_now(),
                    dawn_warning=dawn_warning,
                    warning_msg="Guide star too bright; gain and exposure at minimum",
                )

        status = GuideMonitorStatus.DAWN_WARNING if dawn_warning else GuideMonitorStatus.ADJUSTED
        return GuideMonitorResult(
            status=status,
            exposure_ms=self._cur_exp_ms,
            gain=self._cur_gain,
            max_frac=signal,
            checked_at=_utc_now(),
            dawn_warning=dawn_warning,
            warning_msg="Sky brightening — consider ending session" if dawn_warning else None,
        )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
