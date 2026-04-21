"""
S0-6: MountPort.stop() + emergency-stop cancellation — unit tests.

Calling runner.stop() during a slew must halt the mount and raise WorkflowError
so the session fails cleanly rather than hanging forever.
"""
from unittest.mock import Mock, patch

import pytest

import smart_telescope.workflow.runner as runner_module
from smart_telescope.ports.mount import MountPort
from smart_telescope.workflow.runner import WorkflowError
from tests.conftest import make_unit_runner


class TestMountPortStop:
    def test_mount_port_has_stop_method(self) -> None:
        m = Mock(spec=MountPort)
        assert hasattr(m, "stop")


class TestRunnerStop:
    def test_runner_has_stop_method(self) -> None:
        runner = make_unit_runner()
        assert callable(getattr(runner, "stop", None))

    def test_stop_sets_internal_event(self) -> None:
        runner = make_unit_runner()
        assert not runner._stop_event.is_set()
        runner.stop()
        assert runner._stop_event.is_set()

    def test_stop_calls_mount_stop(self) -> None:
        mount = Mock(spec=MountPort, **{
            "connect.return_value": True,
            "get_state.return_value": __import__(
                "smart_telescope.ports.mount", fromlist=["MountState"]
            ).MountState.PARKED,
            "unpark.return_value": True,
            "enable_tracking.return_value": True,
            "sync.return_value": True,
            "goto.return_value": True,
            "is_slewing.return_value": False,
            "get_position.return_value": __import__(
                "smart_telescope.ports.mount", fromlist=["MountPosition"]
            ).MountPosition(ra=0.0, dec=0.0),
        })
        runner = make_unit_runner(mount=mount)
        runner.stop()
        mount.stop.assert_called_once()


class TestCancellationDuringSlew:
    def test_stop_during_slew_raises_workflow_error(self) -> None:
        """
        Simulate the runner polling is_slewing while another thread calls stop().
        The slew poll must detect the stop_event and raise WorkflowError.
        """
        mount = Mock(spec=MountPort, **{
            "connect.return_value": True,
            "is_slewing.return_value": True,
        })
        runner = make_unit_runner(mount=mount)

        # Set the stop event before entering the poll loop so it's caught immediately
        runner._stop_event.set()

        with (
            patch("smart_telescope.workflow.runner.time.sleep"),
            patch.object(runner_module, "SLEW_TIMEOUT_S", 120.0),
            pytest.raises(WorkflowError) as exc,
        ):
            runner._wait_for_slew("goto")

        assert exc.value.stage == "goto"
        assert "stop" in exc.value.reason.lower() or "cancel" in exc.value.reason.lower()

    def test_stop_event_cleared_before_each_run(self) -> None:
        """A reused runner must not carry stop state into a new run."""
        runner = make_unit_runner()
        runner.stop()
        assert runner._stop_event.is_set()
        runner.run()
        assert not runner._stop_event.is_set()
