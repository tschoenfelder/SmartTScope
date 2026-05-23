"""Latest-frame mailbox and background-capture wrapper for guide camera roles."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..ports.camera import CameraPort
    from ..domain.frame import FitsFrame


@dataclass(frozen=True)
class MailboxFrame:
    """A single captured frame as stored in the mailbox."""
    sequence: int
    captured_at_monotonic: float
    frame: "FitsFrame"
    dropped_before: int = 0


class FrameMailbox:
    """Single-slot latest-frame mailbox.

    Callers that produce frames faster than the consumer can read them see
    intermediate frames silently dropped.  `dropped_count` counts total drops.
    """

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._pending: MailboxFrame | None = None
        self._dropped: int = 0

    def put(self, frame: "FitsFrame", *, sequence: int, captured_at: float) -> None:
        with self._cond:
            if self._pending is not None:
                self._dropped += 1
            self._pending = MailboxFrame(sequence, captured_at, frame, self._dropped)
            self._cond.notify_all()

    def wait_latest(self, *, after_sequence: int = 0, timeout_s: float = 0.2) -> MailboxFrame | None:
        deadline = time.monotonic() + timeout_s
        with self._cond:
            while True:
                if self._pending is not None and self._pending.sequence > after_sequence:
                    frame = self._pending
                    self._pending = None
                    return frame
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self._cond.wait(timeout=remaining)

    @property
    def dropped_count(self) -> int:
        with self._cond:
            return self._dropped


class ManagedCamera:
    """Wraps a CameraPort with a background capture thread and latest-frame mailbox."""

    def __init__(self, camera: "CameraPort", role: str) -> None:
        self.camera = camera
        self.role = role
        self.mailbox = FrameMailbox()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._seq = 0
        self._error: Exception | None = None
        self._err_lock = threading.Lock()

    def start_stream(self, exposure_s: float, cadence_s: float) -> None:
        if self._thread is not None and self._thread.is_alive():
            return  # already running; no-op
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            args=(exposure_s, cadence_s),
            daemon=True,
            name=f"guide-cam-{self.role}",
        )
        self._thread.start()

    def stop_stream(self) -> None:
        self._stop_event.set()
        self.camera.abort_capture()
        if self._thread is not None:
            self._thread.join(timeout=10.0)
            if self._thread.is_alive():
                import logging
                logging.getLogger(__name__).warning(
                    "guide-cam-%s thread did not exit within 10 s", self.role
                )
            self._thread = None

    def pop_stream_error(self) -> Exception | None:
        with self._err_lock:
            err, self._error = self._error, None
            return err

    def _run(self, exposure_s: float, cadence_s: float) -> None:
        from ..ports.camera import CaptureAbortedError

        while not self._stop_event.is_set():
            try:
                cycle_start = time.monotonic()
                frame = self.camera.capture(exposure_s)
                captured_at = time.monotonic()   # after capture to reflect true frame age
                self._seq += 1
                self.mailbox.put(frame, sequence=self._seq, captured_at=captured_at)
                elapsed = time.monotonic() - cycle_start
                sleep_s = max(0.0, cadence_s - elapsed)
                if sleep_s > 0:
                    self._stop_event.wait(timeout=sleep_s)
            except CaptureAbortedError:
                break
            except Exception as exc:
                with self._err_lock:
                    self._error = exc
                break
