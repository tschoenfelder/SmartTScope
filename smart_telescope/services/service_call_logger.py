"""ServiceCallLogger — structured per-call logging to section loggers (M8-015 / REQ-LOG-002).

Usage::

    with rt.service_call_logger.call(
        "auto_gain", "AutoGainService",
        request_payload={"mode": "DSO", "max_iterations": 12},
    ) as scl:
        result = AutoGainService.run_one_shot(...)
        scl.set_response({"status": "OK", "exposure_ms": result.exposure_ms})

If an exception escapes the with-block, status is automatically "failed".
For caught exceptions that prevent normal exit, call scl.set_error(msg) before
returning early — this marks the record as "failed" without re-raising.
"""
from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from types import TracebackType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .section_logger import SectionLogger

from ..domain.service_call_log import ServiceCallRecord

_log = logging.getLogger(__name__)


class _CallContext:
    """Context manager for one service-call log record."""

    def __init__(
        self,
        section_logger: SectionLogger,
        session_id: str,
        section: str,
        service_name: str,
        run_id: str,
        iteration: int,
        request_payload: dict,
        input_frame_filename: str | None,
    ) -> None:
        self._section_logger  = section_logger
        self._session_id      = session_id
        self._section         = section
        self._service_name    = service_name
        self._run_id          = run_id
        self._iteration       = iteration
        self._request_payload = request_payload
        self._input_frame     = input_frame_filename
        self._start_ms        = time.monotonic() * 1000
        self._timestamp       = datetime.now(timezone.utc).isoformat()
        self._response: dict | None = None
        self._explicit_error: str | None = None
        self._cancelled       = False

    # ── public control ────────────────────────────────────────────────────────

    def set_response(self, payload: dict) -> None:
        """Attach a response payload to emit on exit."""
        self._response = payload

    def set_error(self, error: str) -> None:
        """Mark call as failed (for caught exceptions that exit early via return)."""
        self._explicit_error = error

    def mark_cancelled(self) -> None:
        """Mark call as cancelled."""
        self._cancelled = True

    # ── context manager ───────────────────────────────────────────────────────

    def __enter__(self) -> "_CallContext":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        duration_ms = time.monotonic() * 1000 - self._start_ms

        if self._explicit_error is not None:
            status = "failed"
            error  = self._explicit_error
        elif self._cancelled:
            status = "cancelled"
            error  = None
        elif exc_val is not None:
            status = "failed"
            error  = f"{type(exc_val).__name__}: {exc_val}"
        else:
            status = "ok"
            error  = None

        rec = ServiceCallRecord(
            session_id=self._session_id[:8],
            service_name=self._service_name,
            run_id=self._run_id,
            iteration=self._iteration,
            timestamp=self._timestamp,
            input_frame_filename=self._input_frame,
            request_payload=self._request_payload,
            response_payload=self._response,
            duration_ms=round(duration_ms, 1),
            status=status,
            error_if_any=error,
        )
        try:
            self._section_logger.get(self._section).info("%s", rec.to_json_line())
        except Exception as exc:
            _log.warning("ServiceCallLogger: failed to write record: %s", exc)


class ServiceCallLogger:
    """Structured per-call logging wired to the session's SectionLogger.

    One ServiceCallLogger lives on RuntimeContext for the lifetime of the
    application session.  Call .call() to open a context manager that
    writes one ServiceCallRecord (JSON line) to the matching section logger
    on exit.
    """

    def __init__(self, section_logger: SectionLogger, session_id: str) -> None:
        self._section_logger = section_logger
        self._session_id     = session_id

    def call(
        self,
        section: str,
        service_name: str,
        request_payload: dict | None = None,
        input_frame_filename: str | None = None,
        run_id: str | None = None,
        iteration: int = 0,
    ) -> _CallContext:
        """Open a service-call log context manager.

        Args:
            section:               Section name (one of LOG_SECTIONS).
            service_name:          Human-readable service class/function name.
            request_payload:       Dict of inputs (no image data — use filename).
            input_frame_filename:  Path to input FITS frame (if applicable).
            run_id:                Caller-supplied run ID; generated if None.
            iteration:             0-based iteration index within one run.
        """
        return _CallContext(
            section_logger=self._section_logger,
            session_id=self._session_id,
            section=section,
            service_name=service_name,
            run_id=run_id or str(uuid.uuid4())[:8],
            iteration=iteration,
            request_payload=request_payload or {},
            input_frame_filename=input_frame_filename,
        )
