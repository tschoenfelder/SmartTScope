"""R4-005..007: Camera role-based selection across autogain, autofocus, preview WS.

Covers two-camera and three-camera/OAG setups.  Each test verifies that a
camera_role string is resolved to the correct SDK camera index before any
hardware call is made, and that the old camera_index path still works for
backward compatibility.
"""
from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock, patch

import numpy as np
import pytest
from fastapi.testclient import TestClient

from smart_telescope.api import autogain as ag_mod
from smart_telescope.api import deps
from smart_telescope.app import app
from smart_telescope.domain.frame import FitsFrame
from smart_telescope.ports.camera import CameraPort
from smart_telescope.ports.focuser import FocuserPort
from smart_telescope.services.optical_train_registry import OpticalTrain, OpticalTrainRegistry

client = TestClient(app)


# ── factories ─────────────────────────────────────────────────────────────────

def _train(name: str, role: str, idx: int, has_focuser: bool = False) -> OpticalTrain:
    return OpticalTrain(
        name=name, camera_role=role, camera_index=idx,
        telescope_name="c8", focal_mm=2032.0, reducer_factor=1.0,
        pixel_scale_arcsec=0.38, has_focuser=has_focuser,
        focuser="onstep" if has_focuser else "",
    )


def _registry_2cam() -> OpticalTrainRegistry:
    """Two-train setup: main→0, guide→1."""
    return OpticalTrainRegistry({
        "main":  _train("main",  "main",  0, has_focuser=True),
        "guide": _train("guide", "guide", 1),
    })


def _registry_3cam() -> OpticalTrainRegistry:
    """Three-train setup: main→0, guide→1, oag→2."""
    return OpticalTrainRegistry({
        "main":  _train("main",  "main",  0, has_focuser=True),
        "guide": _train("guide", "guide", 1),
        "oag":   _train("oag",   "oag",   2, has_focuser=True),
    })


def _small_frame() -> FitsFrame:
    pixels = np.random.default_rng(7).uniform(100, 60000, (48, 64)).astype(np.float32)
    return FitsFrame(pixels=pixels, header={}, exposure_seconds=2.0)


def _mock_preview_cam(captured: list[int]):
    """Return a side_effect callable that records camera indices.

    Deliberately leaves diagnostic methods (get_bit_depth, get_logical_name, …)
    as MagicMock defaults so camera_info / histogram sends fail silently — the
    same behaviour as the existing test fixtures — ensuring the first WS message
    is the JPEG bytes frame.
    """
    def _spy(idx: int) -> MagicMock:
        captured.append(idx)
        cam = MagicMock(spec=CameraPort)
        cam.capture.return_value = _small_frame()
        return cam
    return _spy


def _available_focuser() -> MagicMock:
    f = MagicMock(spec=FocuserPort)
    type(f).is_available = PropertyMock(return_value=True)
    f.get_position.return_value = 1000
    f.is_moving.return_value = False
    f.get_max_position.return_value = 50000
    return f


@pytest.fixture(autouse=True)
def _reset() -> None:
    ag_mod._reset()
    deps.reset()
    yield
    ag_mod._reset()
    app.dependency_overrides.clear()
    deps.reset()


# ── Autogain camera_role resolution ───────────────────────────────────────────

class TestAutogainCameraRole:
    """POST /api/autogain/run with camera_role resolves to correct camera_index."""

    def _submit_spy(self, captured_resources: list[set]):
        """Returns a job_manager.submit replacement that records claimed resources."""
        def _spy(name, resources, fn, *args, **kwargs):
            captured_resources.append(set(resources))
            return MagicMock()
        return _spy

    def test_role_main_claims_camera_0(self) -> None:
        registry = _registry_2cam()
        captured: list[set] = []
        from smart_telescope.runtime import get_runtime
        with patch.object(deps, "get_optical_train_registry", return_value=registry):
            with patch.object(get_runtime().job_manager, "submit", side_effect=self._submit_spy(captured)):
                r = client.post("/api/autogain/run", json={"camera_role": "main"})
        assert r.status_code == 202
        assert captured and "camera:0" in captured[0]

    def test_role_guide_claims_camera_1(self) -> None:
        registry = _registry_2cam()
        captured: list[set] = []
        from smart_telescope.runtime import get_runtime
        with patch.object(deps, "get_optical_train_registry", return_value=registry):
            with patch.object(get_runtime().job_manager, "submit", side_effect=self._submit_spy(captured)):
                r = client.post("/api/autogain/run", json={"camera_role": "guide"})
        assert r.status_code == 202
        assert captured and "camera:1" in captured[0]

    def test_role_oag_claims_camera_2_three_cam(self) -> None:
        registry = _registry_3cam()
        captured: list[set] = []
        from smart_telescope.runtime import get_runtime
        with patch.object(deps, "get_optical_train_registry", return_value=registry):
            with patch.object(get_runtime().job_manager, "submit", side_effect=self._submit_spy(captured)):
                r = client.post("/api/autogain/run", json={"camera_role": "oag"})
        assert r.status_code == 202
        assert captured and "camera:2" in captured[0]

    def test_unknown_role_falls_back_to_explicit_camera_index(self) -> None:
        registry = _registry_2cam()
        captured: list[set] = []
        from smart_telescope.runtime import get_runtime
        with patch.object(deps, "get_optical_train_registry", return_value=registry):
            with patch.object(get_runtime().job_manager, "submit", side_effect=self._submit_spy(captured)):
                r = client.post("/api/autogain/run", json={"camera_role": "doesnotexist", "camera_index": 5})
        assert r.status_code == 202
        assert captured and "camera:5" in captured[0]

    def test_camera_index_backward_compat_without_role(self) -> None:
        captured: list[set] = []
        from smart_telescope.runtime import get_runtime
        with patch.object(get_runtime().job_manager, "submit", side_effect=self._submit_spy(captured)):
            r = client.post("/api/autogain/run", json={"camera_index": 3})
        assert r.status_code == 202
        assert captured and "camera:3" in captured[0]


# ── Autofocus camera_role resolution ──────────────────────────────────────────

class TestAutofocusCameraRole:
    """POST /api/focuser/autofocus with camera_role uses the correct camera."""

    _AF_RESULT = {"best_position": 1000, "fitted": False, "metric_gain": 0.5, "positions": []}

    def _run_af(self, json_body: dict, registry=None) -> tuple[int, list[int]]:
        captured: list[int] = []

        def _spy(idx: int) -> MagicMock:
            captured.append(idx)
            return MagicMock(spec=CameraPort)

        app.dependency_overrides[deps.get_focuser] = lambda: _available_focuser()

        patches = [
            patch.object(deps, "get_preview_camera", side_effect=_spy),
            patch("smart_telescope.api.focuser.run_autofocus",
                  return_value=MagicMock(to_dict=lambda: self._AF_RESULT)),
        ]
        if registry is not None:
            patches.append(patch.object(deps, "get_optical_train_registry", return_value=registry))

        with patches[0]:
            with patches[1]:
                ctx = patches[2] if len(patches) > 2 else None
                if ctx:
                    with ctx:
                        r = client.post("/api/focuser/autofocus", json=json_body)
                else:
                    r = client.post("/api/focuser/autofocus", json=json_body)

        return r.status_code, captured

    def test_role_guide_uses_camera_index_1(self) -> None:
        status, captured = self._run_af(
            {"camera_role": "guide", "range_steps": 100, "step_size": 10, "exposure": 1.0},
            registry=_registry_2cam(),
        )
        assert status == 200
        assert captured == [1]

    def test_role_oag_uses_camera_index_2_three_cam(self) -> None:
        status, captured = self._run_af(
            {"camera_role": "oag", "range_steps": 100, "step_size": 10, "exposure": 1.0},
            registry=_registry_3cam(),
        )
        assert status == 200
        assert captured == [2]

    def test_camera_index_backward_compat(self) -> None:
        status, captured = self._run_af(
            {"camera_index": 4, "range_steps": 100, "step_size": 10, "exposure": 1.0},
        )
        assert status == 200
        assert captured == [4]


# ── Preview WS camera_role resolution ─────────────────────────────────────────

class TestPreviewWsCameraRole:
    """WebSocket /ws/preview?camera_role=X resolves to correct camera_index."""

    def test_role_guide_opens_camera_1(self) -> None:
        registry = _registry_2cam()
        captured: list[int] = []
        spy = _mock_preview_cam(captured)

        with patch.object(deps, "get_optical_train_registry", return_value=registry):
            with patch.object(deps, "get_preview_camera", side_effect=spy):
                with TestClient(app).websocket_connect("/ws/preview?camera_role=guide") as ws:
                    ws.receive_bytes()

        assert captured and captured[0] == 1

    def test_role_main_opens_camera_0(self) -> None:
        registry = _registry_2cam()
        captured: list[int] = []
        spy = _mock_preview_cam(captured)

        with patch.object(deps, "get_optical_train_registry", return_value=registry):
            with patch.object(deps, "get_preview_camera", side_effect=spy):
                with TestClient(app).websocket_connect("/ws/preview?camera_role=main") as ws:
                    ws.receive_bytes()

        assert captured and captured[0] == 0

    def test_role_oag_opens_camera_2_three_cam(self) -> None:
        registry = _registry_3cam()
        captured: list[int] = []
        spy = _mock_preview_cam(captured)

        with patch.object(deps, "get_optical_train_registry", return_value=registry):
            with patch.object(deps, "get_preview_camera", side_effect=spy):
                with TestClient(app).websocket_connect("/ws/preview?camera_role=oag") as ws:
                    ws.receive_bytes()

        assert captured and captured[0] == 2

    def test_camera_index_param_still_works(self) -> None:
        """Backward compat: camera_index=2 without camera_role → opens camera 2."""
        captured: list[int] = []
        spy = _mock_preview_cam(captured)

        with patch.object(deps, "get_preview_camera", side_effect=spy):
            with TestClient(app).websocket_connect("/ws/preview?camera_index=2") as ws:
                ws.receive_bytes()

        assert captured and captured[0] == 2


# ── OpticalTrainRegistry multi-train query consistency ────────────────────────

class TestRegistryMultiTrain:
    """R4-007: Registry correctly reports all trains in 2-cam and 3-cam setups."""

    def test_two_cam_registry_has_focuser_only_on_main(self) -> None:
        reg = _registry_2cam()
        assert reg.main() is not None
        assert reg.main().has_focuser is True
        assert reg.guide().has_focuser is False

    def test_three_cam_registry_has_focuser_on_main_and_oag(self) -> None:
        reg = _registry_3cam()
        trains_with_focuser = [t for t in reg.all() if t.has_focuser]
        assert len(trains_with_focuser) == 2
        names = {t.name for t in trains_with_focuser}
        assert names == {"main", "oag"}

    def test_by_camera_role_works_in_three_cam(self) -> None:
        reg = _registry_3cam()
        assert reg.by_camera_role("main").camera_index == 0
        assert reg.by_camera_role("guide").camera_index == 1
        assert reg.by_camera_role("oag").camera_index == 2

    def test_by_camera_index_works_in_three_cam(self) -> None:
        reg = _registry_3cam()
        assert reg.by_camera_index(0).name == "main"
        assert reg.by_camera_index(1).name == "guide"
        assert reg.by_camera_index(2).name == "oag"
        assert reg.by_camera_index(99) is None
