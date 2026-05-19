"""JobManager — central registry for long-running background operations.

Two submission modes:

  submit()  — JobManager owns the thread.  Pass the callable; resources are
              claimed before the thread starts and released when it exits.
              A timeout companion thread signals cancellation if the job runs
              too long.

  claim()   — Caller owns the thread.  JobManager tracks resources and status.
              Caller must call release() when the job finishes (use try/finally).

Both modes raise ResourceConflictError if any requested resource is already
held by another running or pending job.

Resource names are plain strings; by convention:

  "camera:N"   specific camera SDK index
  "mount"      the OnStep mount serial bus
  "focuser"    the OnStep focuser channel
"""

from __future__ import annotations

import dataclasses
import logging
import threading
import time
import uuid
from collections.abc import Callable
from enum import auto, Enum
from typing import Any

_log = logging.getLogger(__name__)


class JobStatus(str, Enum):
    PENDING   = "pending"
    RUNNING   = "running"
    DONE      = "done"
    FAILED    = "failed"
    CANCELLED = "cancelled"


class ResourceConflictError(Exception):
    """Raised when a job tries to claim a resource held by another job."""


@dataclasses.dataclass
class Job:
    job_id:     str
    name:       str
    resources:  frozenset[str]
    status:     JobStatus
    cancel:     threading.Event
    started_at: float                    # time.monotonic()
    timeout_s:  float | None = None
    error:      str | None   = None
    _thread:    threading.Thread | None  = dataclasses.field(default=None, repr=False)

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def elapsed_s(self) -> float:
        return time.monotonic() - self.started_at


class JobManager:
    """Thread-safe resource registry and lifecycle manager.

    Typical usage (fully managed)::

        jm = JobManager()
        job = jm.submit("autogain", {"camera:0"}, worker_fn, arg1, timeout_s=300)
        # worker_fn(arg1) runs in a daemon thread
        # check job.status or job.cancel.is_set() from the worker

    Typical usage (caller-managed thread)::

        job = jm.claim("session", {"camera:0", "mount", "focuser"})
        thread = threading.Thread(target=lambda: (runner.run(), jm.release(job.job_id)))
        thread.start()
    """

    def __init__(self) -> None:
        self._lock:  threading.Lock       = threading.Lock()
        self._jobs:  dict[str, Job]       = {}

    # ── fully managed submission ──────────────────────────────────────────────

    def submit(
        self,
        name: str,
        resources: set[str],
        fn: Callable[..., None],
        *args: Any,
        cancel_event: threading.Event | None = None,
        timeout_s: float | None = None,
        **kwargs: Any,
    ) -> Job:
        """Check resources, start *fn* in a daemon thread, return the Job handle.

        *cancel_event* — supply an existing Event to bridge with external cancel
        mechanisms.  If omitted, a new Event is created and attached to the Job.

        The fn is called as ``fn(*args, **kwargs)``.  It should poll
        ``job.cancel.is_set()`` at safe checkpoints to honour cancellation.
        """
        cancel = cancel_event if cancel_event is not None else threading.Event()
        job = self._register(name, frozenset(resources), cancel, timeout_s)

        def _wrapper() -> None:
            try:
                fn(*args, **kwargs)
                with self._lock:
                    if job.status == JobStatus.RUNNING:
                        job.status = JobStatus.DONE
            except Exception as exc:
                _log.error("Job %s (%s) raised: %s", job.job_id, job.name, exc)
                with self._lock:
                    if job.status in (JobStatus.RUNNING, JobStatus.PENDING):
                        job.status = JobStatus.FAILED
                        job.error  = str(exc)
            finally:
                _log.info("Job %s (%s) finished: %s", job.job_id, job.name, job.status.value)

        thread = threading.Thread(
            target=_wrapper,
            daemon=True,
            name=f"job-{name}-{job.job_id}",
        )
        job._thread = thread
        thread.start()

        if timeout_s is not None:
            self._start_timeout_watcher(job, timeout_s)

        _log.info("Job %s (%s) started: resources=%s timeout=%ss",
                  job.job_id, name, resources, timeout_s)
        return job

    # ── caller-managed thread ─────────────────────────────────────────────────

    def claim(
        self,
        name: str,
        resources: set[str],
        cancel_event: threading.Event | None = None,
    ) -> Job:
        """Claim resources without starting a thread.

        The caller is responsible for starting the thread and calling
        ``release(job.job_id)`` when the work is finished.
        """
        cancel = cancel_event if cancel_event is not None else threading.Event()
        job = self._register(name, frozenset(resources), cancel, timeout_s=None)
        _log.info("Job %s (%s) claimed: resources=%s", job.job_id, name, resources)
        return job

    def release(self, job_id: str, *, error: str | None = None) -> None:
        """Mark a claim()-based job as done (or failed if error is supplied)."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            if job.status in (JobStatus.RUNNING, JobStatus.PENDING):
                job.status = JobStatus.FAILED if error else JobStatus.DONE
                if error:
                    job.error = error
        _log.info("Job %s (%s) released: %s", job_id,
                  job.name if job else "?", error or "done")

    # ── cancellation ──────────────────────────────────────────────────────────

    def cancel(self, job_id: str) -> bool:
        """Signal cancellation.  Returns True if the job was found and active."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status not in (JobStatus.RUNNING, JobStatus.PENDING):
                return False
            job.status = JobStatus.CANCELLED
            job.cancel.set()
        _log.info("Job %s (%s): cancel requested", job_id, job.name)
        return True

    def cancel_by_name(self, name: str) -> int:
        """Cancel all active jobs with *name*. Returns count signalled."""
        with self._lock:
            targets = [j for j in self._jobs.values()
                       if j.name == name
                       and j.status in (JobStatus.RUNNING, JobStatus.PENDING)]
            for j in targets:
                j.status = JobStatus.CANCELLED
                j.cancel.set()
        for j in targets:
            _log.info("Job %s (%s): cancel requested by name", j.job_id, j.name)
        return len(targets)

    def cancel_all(self) -> None:
        """Cancel every active job (called from RuntimeContext.shutdown())."""
        with self._lock:
            for j in self._jobs.values():
                if j.status in (JobStatus.RUNNING, JobStatus.PENDING):
                    j.status = JobStatus.CANCELLED
                    j.cancel.set()

    # ── query ─────────────────────────────────────────────────────────────────

    def get_job(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def get_by_name(self, name: str) -> Job | None:
        """Return the most recently submitted job with *name*, or None."""
        with self._lock:
            matches = [j for j in self._jobs.values() if j.name == name]
        return matches[-1] if matches else None

    def list_active(self) -> list[Job]:
        with self._lock:
            return [j for j in self._jobs.values()
                    if j.status in (JobStatus.RUNNING, JobStatus.PENDING)]

    def active_resources(self) -> set[str]:
        """Return the union of all resources held by active jobs."""
        with self._lock:
            held: set[str] = set()
            for j in self._jobs.values():
                if j.status in (JobStatus.RUNNING, JobStatus.PENDING):
                    held.update(j.resources)
            return held

    def is_resource_held(self, resource: str) -> bool:
        return resource in self.active_resources()

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def purge_finished(self, max_age_s: float = 300.0) -> int:
        """Remove finished jobs older than *max_age_s* to bound memory growth."""
        cutoff = time.monotonic() - max_age_s
        with self._lock:
            to_remove = [
                jid for jid, j in self._jobs.items()
                if j.status not in (JobStatus.RUNNING, JobStatus.PENDING)
                and j.started_at < cutoff
            ]
            for jid in to_remove:
                del self._jobs[jid]
        return len(to_remove)

    # ── internals ─────────────────────────────────────────────────────────────

    def _register(
        self,
        name: str,
        resources: frozenset[str],
        cancel: threading.Event,
        timeout_s: float | None,
    ) -> Job:
        with self._lock:
            self._check_conflicts(name, resources)
            job = Job(
                job_id=str(uuid.uuid4())[:8],
                name=name,
                resources=resources,
                status=JobStatus.RUNNING,
                cancel=cancel,
                started_at=time.monotonic(),
                timeout_s=timeout_s,
            )
            self._jobs[job.job_id] = job
        return job

    def _check_conflicts(self, name: str, resources: frozenset[str]) -> None:
        """Raise ResourceConflictError if any resource is already held. Lock must be held."""
        for j in self._jobs.values():
            if j.status not in (JobStatus.RUNNING, JobStatus.PENDING):
                continue
            overlap = resources & j.resources
            if overlap:
                raise ResourceConflictError(
                    f"Cannot start '{name}': resource(s) {sorted(overlap)} "
                    f"already held by '{j.name}' (job {j.job_id})"
                )

    def _start_timeout_watcher(self, job: Job, timeout_s: float) -> None:
        """Spawn a daemon thread that cancels the job if it runs past timeout_s."""
        def _watch() -> None:
            if not job.cancel.wait(timeout=timeout_s):
                # cancel was not set during the timeout window → enforce it
                _log.warning(
                    "Job %s (%s) timed out after %.0f s — cancelling",
                    job.job_id, job.name, timeout_s,
                )
                with self._lock:
                    if job.status == JobStatus.RUNNING:
                        job.status = JobStatus.CANCELLED
                job.cancel.set()

        threading.Thread(
            target=_watch,
            daemon=True,
            name=f"job-timeout-{job.job_id}",
        ).start()
