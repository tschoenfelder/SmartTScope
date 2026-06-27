"""Tests for ServiceCallLogger and _CallContext (M8-015 / REQ-LOG-002)."""
from __future__ import annotations

import json
import logging

import pytest

from smart_telescope.services.section_logger import SectionLogger
from smart_telescope.services.service_call_logger import ServiceCallLogger


# ── Fixtures ──────────────────────────────────────────────────────────────────

SESSION_ID = "abcd1234-efgh-5678"


@pytest.fixture
def section_logger():
    return SectionLogger(session_id=SESSION_ID)


@pytest.fixture
def scl(section_logger):
    return ServiceCallLogger(section_logger=section_logger, session_id=SESSION_ID)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _capture_section(section_logger: SectionLogger, section: str) -> list[dict]:
    """Capture log records emitted to a section logger."""
    records: list[logging.LogRecord] = []

    class _Handler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    logger = section_logger.get(section)
    logger.logger.addHandler(_Handler())
    return records


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_ok_status_on_clean_exit(scl, section_logger):
    records = _capture_section(section_logger, "auto_gain")
    with scl.call("auto_gain", "AutoGainService") as ctx:
        ctx.set_response({"status": "OK"})
    assert len(records) == 1
    data = json.loads(records[0].getMessage())
    assert data["status"] == "ok"
    assert data["response_payload"] == {"status": "OK"}


def test_failed_status_on_set_error(scl, section_logger):
    records = _capture_section(section_logger, "auto_gain")
    with scl.call("auto_gain", "AutoGainService") as ctx:
        ctx.set_error("boom")
    data = json.loads(records[0].getMessage())
    assert data["status"] == "failed"
    assert data["error_if_any"] == "boom"


def test_failed_status_on_uncaught_exception(scl, section_logger):
    records = _capture_section(section_logger, "auto_gain")
    try:
        with scl.call("auto_gain", "AutoGainService"):
            raise ValueError("oops")
    except ValueError:
        pass
    data = json.loads(records[0].getMessage())
    assert data["status"] == "failed"
    assert "ValueError" in data["error_if_any"]


def test_cancelled_status(scl, section_logger):
    records = _capture_section(section_logger, "auto_gain")
    with scl.call("auto_gain", "AutoGainService") as ctx:
        ctx.mark_cancelled()
    data = json.loads(records[0].getMessage())
    assert data["status"] == "cancelled"
    assert data["error_if_any"] is None


def test_explicit_error_beats_no_exception(scl, section_logger):
    """set_error() → failed even when no exception propagates."""
    records = _capture_section(section_logger, "auto_gain")
    with scl.call("auto_gain", "AutoGainService") as ctx:
        ctx.set_error("caught locally")
        # no exception raised here — caller returned early in real code
    data = json.loads(records[0].getMessage())
    assert data["status"] == "failed"
    assert data["error_if_any"] == "caught locally"


def test_request_payload_recorded(scl, section_logger):
    records = _capture_section(section_logger, "plate_solve")
    with scl.call("plate_solve", "SolverPort.solve",
                  request_payload={"exposure_s": 5.0, "radius": None}):
        pass
    data = json.loads(records[0].getMessage())
    assert data["request_payload"]["exposure_s"] == 5.0


def test_input_frame_filename_recorded(scl, section_logger):
    records = _capture_section(section_logger, "plate_solve")
    with scl.call("plate_solve", "SolverPort.solve",
                  input_frame_filename="/data/frame_001.fits"):
        pass
    data = json.loads(records[0].getMessage())
    assert data["input_frame_filename"] == "/data/frame_001.fits"


def test_duration_ms_positive(scl, section_logger):
    records = _capture_section(section_logger, "autofocus")
    with scl.call("autofocus", "run_autofocus"):
        pass
    data = json.loads(records[0].getMessage())
    assert data["duration_ms"] >= 0.0


def test_session_id_truncated_to_8_chars(scl, section_logger):
    records = _capture_section(section_logger, "autofocus")
    with scl.call("autofocus", "run_autofocus"):
        pass
    data = json.loads(records[0].getMessage())
    assert data["session_id"] == SESSION_ID[:8]


def test_run_id_generated_if_not_provided(scl, section_logger):
    records = _capture_section(section_logger, "mount")
    with scl.call("mount", "MountPort.connect"):
        pass
    data = json.loads(records[0].getMessage())
    assert isinstance(data["run_id"], str)
    assert len(data["run_id"]) > 0


def test_run_id_caller_supplied(scl, section_logger):
    records = _capture_section(section_logger, "mount")
    with scl.call("mount", "MountPort.connect", run_id="my-run-42"):
        pass
    data = json.loads(records[0].getMessage())
    assert data["run_id"] == "my-run-42"


def test_iteration_recorded(scl, section_logger):
    records = _capture_section(section_logger, "plate_solve")
    with scl.call("plate_solve", "SolverPort.solve", iteration=3):
        pass
    data = json.loads(records[0].getMessage())
    assert data["iteration"] == 3


def test_all_eleven_fields_present(scl, section_logger):
    required = {
        "session_id", "service_name", "run_id", "iteration", "timestamp",
        "input_frame_filename", "request_payload", "response_payload",
        "duration_ms", "status", "error_if_any",
    }
    records = _capture_section(section_logger, "auto_gain")
    with scl.call("auto_gain", "AutoGainService"):
        pass
    data = json.loads(records[0].getMessage())
    assert required.issubset(data.keys())


def test_response_payload_none_when_not_set(scl, section_logger):
    records = _capture_section(section_logger, "auto_gain")
    with scl.call("auto_gain", "AutoGainService"):
        pass
    data = json.loads(records[0].getMessage())
    assert data["response_payload"] is None


def test_write_failure_does_not_propagate(scl):
    """A broken section logger must not kill the caller."""
    from smart_telescope.services.service_call_logger import _CallContext

    broken_section_logger = object()  # no .get() method

    ctx = _CallContext(
        section_logger=broken_section_logger,  # type: ignore[arg-type]
        session_id=SESSION_ID,
        section="auto_gain",
        service_name="AutoGainService",
        run_id="x",
        iteration=0,
        request_payload={},
        input_frame_filename=None,
    )
    with ctx:
        pass  # should not raise
