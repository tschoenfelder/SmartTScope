"""
S0-4: Structured logging — unit tests.

Every state transition must emit a named INFO log line so session progress
is observable without a debugger.
"""
import logging

import pytest

from tests.conftest import make_log, make_unit_runner


@pytest.fixture(autouse=True)
def runner_log(caplog: pytest.LogCaptureFixture) -> pytest.LogCaptureFixture:
    caplog.set_level(logging.INFO, logger="smart_telescope.workflow.runner")
    return caplog


class TestStateTransitionLogging:
    def test_connect_emits_connected(self, runner_log: pytest.LogCaptureFixture) -> None:
        make_unit_runner()._stage_connect(make_log())
        assert any("CONNECTED" in r.message for r in runner_log.records)

    def test_mount_init_emits_mount_ready(self, runner_log: pytest.LogCaptureFixture) -> None:
        make_unit_runner()._stage_initialize_mount(make_log())
        assert any("MOUNT_READY" in r.message for r in runner_log.records)

    def test_align_emits_aligned(self, runner_log: pytest.LogCaptureFixture) -> None:
        make_unit_runner()._stage_align(make_log())
        assert any("ALIGNED" in r.message for r in runner_log.records)

    def test_goto_emits_slewed(self, runner_log: pytest.LogCaptureFixture) -> None:
        make_unit_runner()._stage_goto(make_log())
        assert any("SLEWED" in r.message for r in runner_log.records)

    def test_save_emits_saved(self, runner_log: pytest.LogCaptureFixture) -> None:
        make_unit_runner()._stage_save(make_log())
        assert any("SAVED" in r.message for r in runner_log.records)

    def test_all_transition_records_are_info_level(
        self, runner_log: pytest.LogCaptureFixture
    ) -> None:
        make_unit_runner()._stage_connect(make_log())
        state_records = [r for r in runner_log.records if r.levelno != logging.INFO]
        assert not state_records, f"Non-INFO records: {state_records}"
