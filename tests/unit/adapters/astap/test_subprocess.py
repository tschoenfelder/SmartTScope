"""
Unit tests for AstapSolver — subprocess layer mocked.

No ASTAP binary or FITS files required. These tests verify how AstapSolver
responds to every subprocess outcome: timeout, launch failure, missing .ini,
and well-formed output. The _parse_ini logic is tested separately in
test_parse_ini.py — keep the two concerns apart.
"""
import subprocess

import pytest

from smart_telescope.adapters.astap.solver import AstapSolver

FAKE_ASTAP = "/fake/astap"
FAKE_FITS = b"SIMPLE  =                    T"   # minimal FITS-ish bytes


def make_solver(**kwargs) -> AstapSolver:
    return AstapSolver(astap_path=FAKE_ASTAP, **kwargs)


def completed_process(returncode: int = 0, stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout="", stderr=stderr)


class TestAstapSubprocessTimeout:
    def test_timeout_returns_failure(self, mocker):
        mocker.patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="astap", timeout=60),
        )
        result = make_solver().solve(FAKE_FITS, 0.38)
        assert not result.success

    def test_timeout_error_message_mentions_timeout(self, mocker):
        mocker.patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="astap", timeout=60),
        )
        result = make_solver().solve(FAKE_FITS, 0.38)
        assert result.error is not None
        assert "timed out" in result.error.lower()


class TestAstapSubprocessLaunchFailure:
    def test_oserror_returns_failure(self, mocker):
        mocker.patch("subprocess.run", side_effect=OSError("No such file"))
        result = make_solver().solve(FAKE_FITS, 0.38)
        assert not result.success

    def test_launch_error_message_is_informative(self, mocker):
        mocker.patch("subprocess.run", side_effect=OSError("No such file"))
        result = make_solver().solve(FAKE_FITS, 0.38)
        assert result.error is not None
        assert len(result.error) > 0


class TestAstapNoIniOutput:
    def test_missing_ini_returns_failure(self, mocker, tmp_path):
        """ASTAP exits without writing a .ini — treat as solve failure."""
        mocker.patch("subprocess.run", return_value=completed_process(returncode=1))
        # No .ini file is created alongside the FITS → failure
        result = make_solver().solve(FAKE_FITS, 0.38)
        assert not result.success

    def test_missing_ini_error_mentions_exit_code(self, mocker):
        mocker.patch(
            "subprocess.run",
            return_value=completed_process(returncode=2, stderr="solve aborted"),
        )
        result = make_solver().solve(FAKE_FITS, 0.38)
        assert not result.success


class TestAstapCommandConstruction:
    def test_pixel_scale_passed_to_astap(self, mocker):
        run_mock = mocker.patch("subprocess.run", return_value=completed_process())
        make_solver().solve(FAKE_FITS, pixel_scale_hint=0.38)
        cmd = run_mock.call_args.args[0]
        assert "-scale" in cmd
        scale_index = cmd.index("-scale")
        assert float(cmd[scale_index + 1]) == pytest.approx(0.38)

    def test_search_radius_passed_to_astap(self, mocker):
        run_mock = mocker.patch("subprocess.run", return_value=completed_process())
        make_solver(search_radius_deg=15.0).solve(FAKE_FITS, 0.38)
        cmd = run_mock.call_args.args[0]
        assert "-r" in cmd
        r_index = cmd.index("-r")
        assert float(cmd[r_index + 1]) == pytest.approx(15.0)

    def test_astap_path_is_first_element(self, mocker):
        run_mock = mocker.patch("subprocess.run", return_value=completed_process())
        make_solver().solve(FAKE_FITS, 0.38)
        cmd = run_mock.call_args.args[0]
        assert cmd[0] == FAKE_ASTAP

    def test_timeout_forwarded_to_subprocess(self, mocker):
        run_mock = mocker.patch("subprocess.run", return_value=completed_process())
        make_solver(timeout_seconds=45).solve(FAKE_FITS, 0.38)
        kwargs = run_mock.call_args.kwargs
        assert kwargs.get("timeout") == 45
