"""Unit tests for deps.py adapter selection logic."""
from pathlib import Path

import pytest

from smart_telescope.adapters.mock.camera import MockCamera
from smart_telescope.adapters.mock.focuser import MockFocuser
from smart_telescope.adapters.mock.mount import MockMount
from smart_telescope.adapters.simulator.camera import SimulatorCamera
from smart_telescope.adapters.simulator.focuser import SimulatorFocuser
from smart_telescope.adapters.simulator.mount import SimulatorMount
from smart_telescope.api import deps


@pytest.fixture(autouse=True)
def _reset() -> None:
    deps.reset()
    yield
    deps.reset()


# ── mock mode (default) ───────────────────────────────────────────────────────


class TestMockMode:
    def test_camera_is_mock(self) -> None:
        assert isinstance(deps.get_camera(), MockCamera)

    def test_mount_is_mock(self) -> None:
        assert isinstance(deps.get_mount(), MockMount)

    def test_focuser_is_mock(self) -> None:
        assert isinstance(deps.get_focuser(), MockFocuser)


# ── simulator mode (SIMULATOR_FITS_DIR set) ───────────────────────────────────


class TestSimulatorMode:
    def test_camera_is_simulator(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("SIMULATOR_FITS_DIR", str(tmp_path))
        assert isinstance(deps.get_camera(), SimulatorCamera)

    def test_mount_is_simulator(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("SIMULATOR_FITS_DIR", str(tmp_path))
        assert isinstance(deps.get_mount(), SimulatorMount)

    def test_focuser_is_simulator(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("SIMULATOR_FITS_DIR", str(tmp_path))
        assert isinstance(deps.get_focuser(), SimulatorFocuser)

    def test_simulator_camera_receives_data_dir(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("SIMULATOR_FITS_DIR", str(tmp_path))
        cam = deps.get_camera()
        assert isinstance(cam, SimulatorCamera)
        assert cam._data_dir == tmp_path


# ── replay mode (REPLAY_FITS_DIR set) ────────────────────────────────────────


class TestReplayMode:
    def _make_fits_dir(self, tmp_path: Path) -> Path:
        import io
        import numpy as np
        from astropy.io import fits

        d = tmp_path / "replay"
        d.mkdir()
        hdu = fits.PrimaryHDU(np.zeros((32, 32), dtype=np.uint16))
        buf = io.BytesIO()
        hdu.writeto(buf)
        (d / "frame.fits").write_bytes(buf.getvalue())
        return d

    def test_camera_is_replay(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        from smart_telescope.adapters.replay.camera import ReplayCamera
        d = self._make_fits_dir(tmp_path)
        monkeypatch.setenv("REPLAY_FITS_DIR", str(d))
        assert isinstance(deps.get_camera(), ReplayCamera)

    def test_replay_lower_priority_than_simulator(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        d = self._make_fits_dir(tmp_path)
        monkeypatch.setenv("REPLAY_FITS_DIR", str(d))
        monkeypatch.setenv("SIMULATOR_FITS_DIR", str(tmp_path))
        assert isinstance(deps.get_camera(), SimulatorCamera)


# ── ToupTek camera mode (TOUPTEK_INDEX set) ───────────────────────────────────


class TestToupcamMode:
    def test_camera_is_touptek(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from smart_telescope.adapters.touptek.camera import ToupcamCamera

        monkeypatch.setenv("TOUPTEK_INDEX", "0")
        assert isinstance(deps.get_camera(), ToupcamCamera)

    def test_touptek_index_passed_to_adapter(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from smart_telescope.adapters.touptek.camera import ToupcamCamera

        monkeypatch.setenv("TOUPTEK_INDEX", "1")
        cam = deps.get_camera()
        assert isinstance(cam, ToupcamCamera)
        assert cam._index == 1

    def test_touptek_overrides_simulator_for_camera(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        from smart_telescope.adapters.touptek.camera import ToupcamCamera

        monkeypatch.setenv("TOUPTEK_INDEX", "0")
        monkeypatch.setenv("SIMULATOR_FITS_DIR", str(tmp_path))
        assert isinstance(deps.get_camera(), ToupcamCamera)

    def test_touptek_camera_with_onstep_mount(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from smart_telescope.adapters.onstep.mount import OnStepMount
        from smart_telescope.adapters.touptek.camera import ToupcamCamera

        monkeypatch.setenv("TOUPTEK_INDEX", "0")
        monkeypatch.setenv("ONSTEP_PORT", "/dev/ttyUSB0")
        assert isinstance(deps.get_camera(), ToupcamCamera)
        deps.reset()
        assert isinstance(deps.get_mount(), OnStepMount)

    def test_simulator_mount_still_used_when_only_touptek_set(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("TOUPTEK_INDEX", "0")
        monkeypatch.setenv("SIMULATOR_FITS_DIR", str(tmp_path))
        assert isinstance(deps.get_mount(), SimulatorMount)


# ── hardware mode (ONSTEP_PORT set) ───────────────────────────────────────────


class TestHardwareMode:
    def test_mount_is_onstep(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from smart_telescope.adapters.onstep.mount import OnStepMount

        monkeypatch.setenv("ONSTEP_PORT", "/dev/ttyUSB0")
        assert isinstance(deps.get_mount(), OnStepMount)

    def test_focuser_is_onstep(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from smart_telescope.adapters.onstep.focuser import OnStepFocuser

        monkeypatch.setenv("ONSTEP_PORT", "/dev/ttyUSB0")
        assert isinstance(deps.get_focuser(), OnStepFocuser)

    def test_onstep_takes_priority_over_simulator(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        from smart_telescope.adapters.onstep.mount import OnStepMount

        monkeypatch.setenv("ONSTEP_PORT", "/dev/ttyUSB0")
        monkeypatch.setenv("SIMULATOR_FITS_DIR", str(tmp_path))
        assert isinstance(deps.get_mount(), OnStepMount)


# ── singleton caching ─────────────────────────────────────────────────────────


class TestSingletons:
    def test_get_camera_returns_same_instance(self) -> None:
        assert deps.get_camera() is deps.get_camera()

    def test_get_mount_returns_same_instance(self) -> None:
        assert deps.get_mount() is deps.get_mount()

    def test_get_focuser_returns_same_instance(self) -> None:
        assert deps.get_focuser() is deps.get_focuser()

    def test_reset_allows_new_camera_instance(self) -> None:
        cam1 = deps.get_camera()
        deps.reset()
        cam2 = deps.get_camera()
        assert cam1 is not cam2

    def test_reset_allows_new_mount_instance(self) -> None:
        mnt1 = deps.get_mount()
        deps.reset()
        mnt2 = deps.get_mount()
        assert mnt1 is not mnt2

    def test_reset_allows_new_focuser_instance(self) -> None:
        foc1 = deps.get_focuser()
        deps.reset()
        foc2 = deps.get_focuser()
        assert foc1 is not foc2

    def test_simulator_singleton_survives_second_call(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("SIMULATOR_FITS_DIR", str(tmp_path))
        assert deps.get_mount() is deps.get_mount()
