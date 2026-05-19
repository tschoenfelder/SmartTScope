"""
S0-4: Structured logging — unit tests.

Every state transition must emit a named INFO log line so session progress
is observable without a debugger.

The runner._transition method is the log emitter; tests wire it into the
StageContext so stage functions trigger runner logging.
"""
import logging

import pytest

from smart_telescope.workflow.stages import (
    stage_align,
    stage_connect,
    stage_goto,
    stage_initialize_mount,
    stage_save,
)
from tests.conftest import make_log, make_stage_ctx, make_unit_runner


@pytest.fixture(autouse=True)
def runner_log(caplog: pytest.LogCaptureFixture) -> pytest.LogCaptureFixture:
    caplog.set_level(logging.INFO, logger="smart_telescope.workflow.runner")
    return caplog


class TestStateTransitionLogging:
    def test_connect_emits_connected(self, runner_log: pytest.LogCaptureFixture) -> None:
        runner = make_unit_runner()
        ctx = make_stage_ctx(on_transition=runner._transition)
        stage_connect(ctx, make_log())
        assert any("CONNECTED" in r.message for r in runner_log.records)

    def test_mount_init_emits_mount_ready(self, runner_log: pytest.LogCaptureFixture) -> None:
        runner = make_unit_runner()
        ctx = make_stage_ctx(on_transition=runner._transition)
        stage_initialize_mount(ctx, make_log())
        assert any("MOUNT_READY" in r.message for r in runner_log.records)

    def test_align_emits_aligned(self, runner_log: pytest.LogCaptureFixture) -> None:
        runner = make_unit_runner()
        ctx = make_stage_ctx(on_transition=runner._transition)
        stage_align(ctx, make_log())
        assert any("ALIGNED" in r.message for r in runner_log.records)

    def test_goto_emits_slewed(self, runner_log: pytest.LogCaptureFixture) -> None:
        runner = make_unit_runner()
        ctx = make_stage_ctx(on_transition=runner._transition)
        stage_goto(ctx, make_log())
        assert any("SLEWED" in r.message for r in runner_log.records)

    def test_save_emits_saved(self, runner_log: pytest.LogCaptureFixture) -> None:
        runner = make_unit_runner()
        ctx = make_stage_ctx(on_transition=runner._transition)
        stage_save(ctx, make_log())
        assert any("SAVED" in r.message for r in runner_log.records)

    def test_all_transition_records_are_info_level(
        self, runner_log: pytest.LogCaptureFixture
    ) -> None:
        runner = make_unit_runner()
        ctx = make_stage_ctx(on_transition=runner._transition)
        stage_connect(ctx, make_log())
        state_records = [r for r in runner_log.records if r.levelno != logging.INFO]
        assert not state_records, f"Non-INFO records: {state_records}"
