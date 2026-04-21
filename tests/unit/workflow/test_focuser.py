"""
S0-5: FocuserPort + MockFocuser wired into runner — unit tests.

The runner must connect the focuser in the connect stage and surface a named
error when it fails.
"""
from unittest.mock import Mock

import pytest

from smart_telescope.ports.focuser import FocuserPort
from smart_telescope.workflow.runner import WorkflowError
from tests.conftest import make_log, make_unit_runner


@pytest.fixture()
def focuser_mock() -> Mock:
    f = Mock(spec=FocuserPort)
    f.connect.return_value = True
    return f


class TestFocuserPort:
    def test_focuser_port_has_connect_method(self) -> None:
        f = Mock(spec=FocuserPort)
        assert hasattr(f, "connect")

    def test_focuser_port_has_disconnect_method(self) -> None:
        f = Mock(spec=FocuserPort)
        assert hasattr(f, "disconnect")

    def test_focuser_port_has_move_method(self) -> None:
        f = Mock(spec=FocuserPort)
        assert hasattr(f, "move")

    def test_focuser_port_has_get_position_method(self) -> None:
        f = Mock(spec=FocuserPort)
        assert hasattr(f, "get_position")


class TestStageConnectWithFocuser:
    def test_connect_calls_focuser_connect(self, focuser_mock: Mock) -> None:
        runner = make_unit_runner(focuser=focuser_mock)
        runner._stage_connect(make_log())
        focuser_mock.connect.assert_called_once()

    def test_focuser_failure_raises_at_connect_stage(self, focuser_mock: Mock) -> None:
        focuser_mock.connect.return_value = False
        runner = make_unit_runner(focuser=focuser_mock)
        with pytest.raises(WorkflowError) as exc:
            runner._stage_connect(make_log())
        assert exc.value.stage == "connect"
        assert "Focuser" in exc.value.reason

    def test_mount_not_contacted_when_focuser_fails(self, focuser_mock: Mock) -> None:
        """Camera succeeds, focuser fails — mount must not be attempted."""
        from unittest.mock import Mock as M

        from smart_telescope.ports.mount import MountPort
        focuser_mock.connect.return_value = False
        mount_mock = M(spec=MountPort)
        runner = make_unit_runner(focuser=focuser_mock, mount=mount_mock)
        with pytest.raises(WorkflowError):
            runner._stage_connect(make_log())
        mount_mock.connect.assert_not_called()

    def test_run_disconnects_focuser_on_completion(self, focuser_mock: Mock) -> None:
        runner = make_unit_runner(focuser=focuser_mock)
        runner.run()
        focuser_mock.disconnect.assert_called_once()


class TestMockFocuser:
    def test_mock_focuser_connect_returns_true_by_default(self) -> None:
        from smart_telescope.adapters.mock.focuser import MockFocuser
        f = MockFocuser()
        assert f.connect() is True

    def test_mock_focuser_fail_connect(self) -> None:
        from smart_telescope.adapters.mock.focuser import MockFocuser
        f = MockFocuser(fail_connect=True)
        assert f.connect() is False

    def test_mock_focuser_move_changes_position(self) -> None:
        from smart_telescope.adapters.mock.focuser import MockFocuser
        f = MockFocuser()
        f.connect()
        f.move(500)
        assert f.get_position() == 500

    def test_mock_focuser_honours_focuser_port_contract(self) -> None:
        from smart_telescope.adapters.mock.focuser import MockFocuser
        f = MockFocuser()
        assert isinstance(f, FocuserPort)
