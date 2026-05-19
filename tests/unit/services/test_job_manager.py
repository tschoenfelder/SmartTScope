"""Unit tests for JobManager — R3-007."""
from __future__ import annotations

import threading
import time

import pytest

from smart_telescope.services.job_manager import (
    Job,
    JobManager,
    JobStatus,
    ResourceConflictError,
)


# ── submit (fully managed) ────────────────────────────────────────────────────

class TestSubmit:
    def test_returns_job_handle(self):
        jm = JobManager()
        job = jm.submit("test", set(), lambda: None)
        assert isinstance(job, Job)
        time.sleep(0.05)

    def test_job_status_done_after_fn_returns(self):
        jm = JobManager()
        done = threading.Event()
        job = jm.submit("test", set(), lambda: done.set())
        done.wait(timeout=2)
        time.sleep(0.05)  # let wrapper finish status update
        assert job.status == JobStatus.DONE

    def test_job_status_failed_when_fn_raises(self):
        jm = JobManager()
        def _bad():
            raise ValueError("boom")
        job = jm.submit("test", set(), _bad)
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and job.status == JobStatus.RUNNING:
            time.sleep(0.01)
        assert job.status == JobStatus.FAILED
        assert "boom" in (job.error or "")

    def test_submit_raises_on_resource_conflict(self):
        jm = JobManager()
        gate = threading.Event()
        jm.submit("job1", {"camera:0"}, gate.wait)
        with pytest.raises(ResourceConflictError):
            jm.submit("job2", {"camera:0"}, lambda: None)
        gate.set()

    def test_resource_released_after_fn_returns(self):
        jm = JobManager()
        done = threading.Event()
        jm.submit("test", {"camera:0"}, lambda: done.set())
        done.wait(timeout=2)
        time.sleep(0.05)
        # should be able to submit again on the same resource
        job2 = jm.submit("test2", {"camera:0"}, lambda: None)
        assert job2 is not None

    def test_positional_args_passed_to_fn(self):
        jm = JobManager()
        results: list = []
        jm.submit("test", set(), lambda x, y: results.append(x + y), 3, 4)
        time.sleep(0.1)
        assert results == [7]

    def test_kwargs_passed_to_fn(self):
        jm = JobManager()
        results: dict = {}
        def _fn(key, value):
            results[key] = value
        jm.submit("test", set(), _fn, key="k", value="v")
        time.sleep(0.1)
        assert results == {"k": "v"}

    def test_cancel_event_bridged_when_supplied(self):
        jm = JobManager()
        cancel = threading.Event()
        gate = threading.Event()
        job = jm.submit("test", set(), gate.wait, cancel_event=cancel)
        assert job.cancel is cancel
        cancel.set()
        gate.set()


# ── claim / release (caller-managed) ─────────────────────────────────────────

class TestClaimRelease:
    def test_claim_returns_job(self):
        jm = JobManager()
        job = jm.claim("test", {"mount"})
        assert isinstance(job, Job)
        jm.release(job.job_id)

    def test_claim_holds_resource(self):
        jm = JobManager()
        job = jm.claim("test", {"mount"})
        with pytest.raises(ResourceConflictError):
            jm.claim("test2", {"mount"})
        jm.release(job.job_id)

    def test_release_frees_resource(self):
        jm = JobManager()
        job = jm.claim("test", {"mount"})
        jm.release(job.job_id)
        job2 = jm.claim("test2", {"mount"})
        assert job2 is not None
        jm.release(job2.job_id)

    def test_release_sets_done_status(self):
        jm = JobManager()
        job = jm.claim("test", {"mount"})
        jm.release(job.job_id)
        assert job.status == JobStatus.DONE

    def test_release_with_error_sets_failed_status(self):
        jm = JobManager()
        job = jm.claim("test", {"mount"})
        jm.release(job.job_id, error="something went wrong")
        assert job.status == JobStatus.FAILED
        assert job.error == "something went wrong"

    def test_release_unknown_id_is_noop(self):
        jm = JobManager()
        jm.release("nonexistent-id")  # must not raise

    def test_claim_empty_resources_succeeds(self):
        jm = JobManager()
        job = jm.claim("test", set())
        jm.release(job.job_id)


# ── cancellation ──────────────────────────────────────────────────────────────

class TestCancellation:
    def test_cancel_sets_cancel_event(self):
        jm = JobManager()
        gate = threading.Event()
        job = jm.submit("test", set(), gate.wait)
        jm.cancel(job.job_id)
        assert job.cancel.is_set()
        gate.set()

    def test_cancel_sets_cancelled_status(self):
        jm = JobManager()
        gate = threading.Event()
        job = jm.submit("test", set(), gate.wait)
        jm.cancel(job.job_id)
        assert job.status == JobStatus.CANCELLED
        gate.set()

    def test_cancel_returns_true_when_found(self):
        jm = JobManager()
        gate = threading.Event()
        job = jm.submit("test", set(), gate.wait)
        result = jm.cancel(job.job_id)
        assert result is True
        gate.set()

    def test_cancel_returns_false_for_unknown_id(self):
        jm = JobManager()
        assert jm.cancel("no-such-id") is False

    def test_cancel_by_name_cancels_all_matching(self):
        jm = JobManager()
        g1, g2 = threading.Event(), threading.Event()
        job1 = jm.submit("target", set(), g1.wait)
        job2 = jm.submit("target", set(), g2.wait)
        count = jm.cancel_by_name("target")
        assert count == 2
        assert job1.status == JobStatus.CANCELLED
        assert job2.status == JobStatus.CANCELLED
        g1.set()
        g2.set()

    def test_cancel_by_name_ignores_other_names(self):
        jm = JobManager()
        gate = threading.Event()
        job = jm.submit("keep", set(), gate.wait)
        jm.cancel_by_name("other")
        assert job.status == JobStatus.RUNNING
        gate.set()

    def test_cancel_all_cancels_everything(self):
        jm = JobManager()
        g1, g2 = threading.Event(), threading.Event()
        job1 = jm.submit("a", set(), g1.wait)
        job2 = jm.submit("b", set(), g2.wait)
        jm.cancel_all()
        assert job1.status == JobStatus.CANCELLED
        assert job2.status == JobStatus.CANCELLED
        g1.set()
        g2.set()


# ── timeout ───────────────────────────────────────────────────────────────────

class TestTimeout:
    def test_job_cancelled_after_timeout(self):
        jm = JobManager()
        gate = threading.Event()
        job = jm.submit("test", set(), gate.wait, timeout_s=0.1)
        time.sleep(0.3)
        assert job.status == JobStatus.CANCELLED
        gate.set()

    def test_job_not_cancelled_when_fn_finishes_before_timeout(self):
        jm = JobManager()
        job = jm.submit("test", set(), lambda: None, timeout_s=5.0)
        time.sleep(0.1)
        assert job.status == JobStatus.DONE


# ── query ─────────────────────────────────────────────────────────────────────

class TestQuery:
    def test_get_job_returns_job(self):
        jm = JobManager()
        gate = threading.Event()
        job = jm.submit("test", set(), gate.wait)
        assert jm.get_job(job.job_id) is job
        gate.set()

    def test_get_job_returns_none_for_unknown(self):
        jm = JobManager()
        assert jm.get_job("no-such") is None

    def test_get_by_name_returns_job(self):
        jm = JobManager()
        gate = threading.Event()
        job = jm.submit("named", set(), gate.wait)
        found = jm.get_by_name("named")
        assert found is job
        gate.set()

    def test_get_by_name_returns_none_when_not_found(self):
        jm = JobManager()
        assert jm.get_by_name("missing") is None

    def test_list_active_includes_running_jobs(self):
        jm = JobManager()
        gate = threading.Event()
        job = jm.submit("test", set(), gate.wait)
        active = jm.list_active()
        assert job in active
        gate.set()

    def test_list_active_excludes_done_jobs(self):
        jm = JobManager()
        done = threading.Event()
        job = jm.submit("test", set(), lambda: done.set())
        done.wait(timeout=2)
        time.sleep(0.05)
        assert job not in jm.list_active()

    def test_active_resources_includes_held_resources(self):
        jm = JobManager()
        gate = threading.Event()
        jm.submit("test", {"camera:0", "mount"}, gate.wait)
        resources = jm.active_resources()
        assert "camera:0" in resources
        assert "mount" in resources
        gate.set()

    def test_is_resource_held_true_for_active(self):
        jm = JobManager()
        gate = threading.Event()
        jm.submit("test", {"focuser"}, gate.wait)
        assert jm.is_resource_held("focuser")
        gate.set()

    def test_is_resource_held_false_after_release(self):
        jm = JobManager()
        job = jm.claim("test", {"focuser"})
        jm.release(job.job_id)
        assert not jm.is_resource_held("focuser")


# ── conflict detection ────────────────────────────────────────────────────────

class TestConflictDetection:
    def test_done_job_does_not_block_same_resource(self):
        jm = JobManager()
        job = jm.claim("test", {"camera:0"})
        jm.release(job.job_id)
        job2 = jm.claim("test2", {"camera:0"})  # must not raise
        jm.release(job2.job_id)

    def test_non_overlapping_resources_run_concurrently(self):
        jm = JobManager()
        job1 = jm.claim("a", {"camera:0"})
        job2 = jm.claim("b", {"camera:1"})  # no overlap
        jm.release(job1.job_id)
        jm.release(job2.job_id)

    def test_error_message_names_the_holder(self):
        jm = JobManager()
        gate = threading.Event()
        jm.submit("holder", {"camera:0"}, gate.wait)
        with pytest.raises(ResourceConflictError, match="holder"):
            jm.claim("newcomer", {"camera:0"})
        gate.set()

    def test_cancelled_job_does_not_block_resource(self):
        jm = JobManager()
        gate = threading.Event()
        job = jm.submit("test", {"camera:0"}, gate.wait)
        jm.cancel(job.job_id)
        # cancelled — resource should no longer be considered held
        job2 = jm.claim("test2", {"camera:0"})  # must not raise
        jm.release(job2.job_id)
        gate.set()


# ── purge ─────────────────────────────────────────────────────────────────────

class TestPurge:
    def test_purge_removes_finished_jobs(self):
        jm = JobManager()
        job = jm.claim("test", set())
        jm.release(job.job_id)
        removed = jm.purge_finished(max_age_s=0)
        assert removed == 1
        assert jm.get_job(job.job_id) is None

    def test_purge_leaves_active_jobs(self):
        jm = JobManager()
        gate = threading.Event()
        job = jm.submit("test", set(), gate.wait)
        removed = jm.purge_finished(max_age_s=0)
        assert removed == 0
        assert jm.get_job(job.job_id) is not None
        gate.set()

    def test_purge_returns_count(self):
        jm = JobManager()
        for _ in range(3):
            j = jm.claim("test", set())
            jm.release(j.job_id)
        count = jm.purge_finished(max_age_s=0)
        assert count == 3
