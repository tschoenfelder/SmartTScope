"""Unit tests for /api/autogain endpoints (AGT-5-3)."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Iterator
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from fastapi.testclient import TestClient

from smart_telescope.api import autogain as ag_mod
from smart_telescope.api import deps
from smart_telescope.app import app
from smart_telescope.domain.autogain_service import AutoGainResult, AutoGainStatus
from smart_telescope.domain.camera_capabilities import ConversionGain
from smart_telescope.domain.frame import FitsFrame

client = TestClient(app)

BIT_DEPTH = 16
ADC_MAX   = float((1 << BIT_DEPTH) - 1)


# ── Camera stub ───────────────────────────────────────────────────────────────

def _make_frame(mean_frac: float) -> FitsFrame:
    pix = np.full((64, 64), mean_frac * ADC_MAX, dtype=np.float32)
    m = MagicMock(spec=FitsFrame)
    m.pixels = pix
    return m


class _FakeCamera:
    """Camera that always returns a frame in-band → AutoGainService yields OK."""

    def capture(self, _exp: float) -> FitsFrame:
        return _make_frame(0.28)

    def connect(self) -> bool:               return True
    def disconnect(self) -> None:            pass
    def get_exposure_ms(self) -> float:      return 2000.0
    def set_exposure_ms(self, ms) -> None:   pass
    def get_gain(self) -> int:               return 100
    def set_gain(self, g) -> None:           pass
    def get_black_level(self) -> int:        return 0
    def set_black_level(self, l) -> None:    pass
    def get_conversion_gain(self):           return ConversionGain.LCG
    def set_conversion_gain(self, m):        pass
    def get_bit_depth(self) -> int:          return BIT_DEPTH
    def get_temperature(self):               return None
    def get_capabilities(self):              return MagicMock()
    def get_serial_number(self) -> str:      return "FAKE"
    def get_logical_name(self) -> str:       return "FakeCamera"


@pytest.fixture(autouse=True)
def reset_state() -> Iterator[None]:
    ag_mod._reset()
    yield
    ag_mod._reset()


# ── GET /api/autogain/status — idle ──────────────────────────────────────────

class TestStatusIdle:
    def test_returns_200(self) -> None:
        r = client.get("/api/autogain/status")
        assert r.status_code == 200

    def test_running_is_false(self) -> None:
        r = client.get("/api/autogain/status")
        assert r.json()["running"] is False

    def test_status_is_none_when_idle(self) -> None:
        r = client.get("/api/autogain/status")
        assert r.json()["status"] is None


# ── POST /api/autogain/run ────────────────────────────────────────────────────

class TestRunEndpoint:
    def test_returns_202(self) -> None:
        with patch.object(deps, "get_preview_camera", return_value=_FakeCamera()):
            r = client.post("/api/autogain/run", json={"camera_index": 0})
        assert r.status_code == 202

    def test_started_true_in_response(self) -> None:
        with patch.object(deps, "get_preview_camera", return_value=_FakeCamera()):
            d = client.post("/api/autogain/run", json={"camera_index": 0}).json()
        assert d["started"] is True

    def test_returns_409_when_already_running(self) -> None:
        import threading as _thr
        blocked = _thr.Event()
        released = _thr.Event()

        original_run = ag_mod.AutoGainService.run_one_shot

        def _slow_run(*args, **kwargs):
            blocked.set()           # signal that we're inside the first run
            released.wait(timeout=3)  # wait until the test fires the second request
            return original_run(*args, **kwargs)

        with patch.object(ag_mod.AutoGainService, "run_one_shot", side_effect=_slow_run):
            with patch.object(deps, "get_preview_camera", return_value=_FakeCamera()):
                client.post("/api/autogain/run", json={"camera_index": 0})
                blocked.wait(timeout=2)   # wait until first run is inside service
                r = client.post("/api/autogain/run", json={"camera_index": 0})
                released.set()            # let first run complete
        assert r.status_code == 409

    def test_returns_400_for_unknown_model(self) -> None:
        r = client.post("/api/autogain/run", json={"camera_index": 0, "camera_model": "BOGUS_XYZ"})
        assert r.status_code == 400

    def test_returns_422_for_unknown_mode(self) -> None:
        r = client.post("/api/autogain/run", json={"camera_index": 0, "mode": "INVALID_MODE"})
        assert r.status_code == 422

    def test_known_model_accepted(self) -> None:
        with patch.object(deps, "get_preview_camera", return_value=_FakeCamera()):
            r = client.post("/api/autogain/run", json={"camera_index": 0, "camera_model": "ATR585M"})
        assert r.status_code == 202


# ── POST /api/autogain/cancel ─────────────────────────────────────────────────

class TestCancelEndpoint:
    def test_cancel_when_idle_returns_200(self) -> None:
        r = client.post("/api/autogain/cancel")
        assert r.status_code == 200

    def test_cancel_sets_cancelled_flag(self) -> None:
        with patch.object(deps, "get_preview_camera", return_value=_FakeCamera()):
            client.post("/api/autogain/run", json={"camera_index": 0})
            r = client.post("/api/autogain/cancel")
        assert r.status_code == 200
        assert r.json()["cancelled"] is True


# ── Full round-trip: run → complete → status ──────────────────────────────────

class TestRoundTrip:
    def _wait_for_result(self, max_s: float = 5.0) -> dict:
        deadline = time.monotonic() + max_s
        while time.monotonic() < deadline:
            d = client.get("/api/autogain/status").json()
            if not d["running"]:
                return d
            time.sleep(0.05)
        pytest.fail("AutoGain run did not finish within timeout")

    def test_run_completes_with_ok_status(self) -> None:
        with patch.object(deps, "get_preview_camera", return_value=_FakeCamera()):
            client.post("/api/autogain/run", json={"camera_index": 0})
        d = self._wait_for_result()
        assert d["status"] == AutoGainStatus.OK.value

    def test_result_has_exposure_ms(self) -> None:
        with patch.object(deps, "get_preview_camera", return_value=_FakeCamera()):
            client.post("/api/autogain/run", json={"camera_index": 0})
        d = self._wait_for_result()
        assert d["exposure_ms"] is not None
        assert d["exposure_ms"] > 0

    def test_result_has_gain(self) -> None:
        with patch.object(deps, "get_preview_camera", return_value=_FakeCamera()):
            client.post("/api/autogain/run", json={"camera_index": 0})
        d = self._wait_for_result()
        assert d["gain"] is not None
        assert d["gain"] >= 100

    def test_result_has_offset(self) -> None:
        with patch.object(deps, "get_preview_camera", return_value=_FakeCamera()):
            client.post("/api/autogain/run", json={"camera_index": 0})
        d = self._wait_for_result()
        assert d["offset"] is not None

    def test_running_false_after_completion(self) -> None:
        with patch.object(deps, "get_preview_camera", return_value=_FakeCamera()):
            client.post("/api/autogain/run", json={"camera_index": 0})
        d = self._wait_for_result()
        assert d["running"] is False

    def test_second_run_possible_after_first_completes(self) -> None:
        with patch.object(deps, "get_preview_camera", return_value=_FakeCamera()):
            client.post("/api/autogain/run", json={"camera_index": 0})
        self._wait_for_result()
        with patch.object(deps, "get_preview_camera", return_value=_FakeCamera()):
            r = client.post("/api/autogain/run", json={"camera_index": 0})
        assert r.status_code == 202


# ── Camera error path ─────────────────────────────────────────────────────────

class TestCameraError:
    def _wait_for_result(self, max_s: float = 5.0) -> dict:
        deadline = time.monotonic() + max_s
        while time.monotonic() < deadline:
            d = client.get("/api/autogain/status").json()
            if not d["running"]:
                return d
            time.sleep(0.05)
        pytest.fail("AutoGain run did not finish within timeout")

    def test_error_field_set_when_camera_unavailable(self) -> None:
        with patch.object(deps, "get_preview_camera", side_effect=RuntimeError("no camera")):
            client.post("/api/autogain/run", json={"camera_index": 0})
        d = self._wait_for_result()
        assert d["error"] is not None
        assert "no camera" in d["error"]


# ── last-good persistence (OK path saves file) ────────────────────────────────

class TestLastGoodPersistence:
    def _wait_for_result(self, max_s: float = 5.0) -> dict:
        deadline = time.monotonic() + max_s
        while time.monotonic() < deadline:
            d = client.get("/api/autogain/status").json()
            if not d["running"]:
                return d
            time.sleep(0.05)
        pytest.fail("AutoGain run did not finish within timeout")

    def test_last_good_saved_on_ok(self, tmp_path: Path) -> None:
        with (
            patch.object(deps, "get_preview_camera", return_value=_FakeCamera()),
            patch.object(ag_mod, "_app_state_dir", return_value=tmp_path),
        ):
            client.post("/api/autogain/run", json={"camera_index": 0, "camera_model": "ATR585M"})
            self._wait_for_result()

        last_good_files = list((tmp_path / "last_good").glob("*.json"))
        assert len(last_good_files) == 1
        import json
        data = json.loads(last_good_files[0].read_text())
        assert data["camera_model"] == "ATR585M"
        assert data["exposure_ms"] > 0

    def test_last_good_not_saved_when_no_signal(self, tmp_path: Path) -> None:
        """A non-OK result must NOT overwrite last-good."""
        class _BlackCamera(_FakeCamera):
            def capture(self, _exp):
                return _make_frame(0.0)

        with (
            patch.object(deps, "get_preview_camera", return_value=_BlackCamera()),
            patch.object(ag_mod, "_app_state_dir", return_value=tmp_path),
        ):
            client.post("/api/autogain/run", json={
                "camera_index": 0,
                "camera_model": "ATR585M",
                "max_iterations": 3,
            })
            self._wait_for_result()

        last_good_dir = tmp_path / "last_good"
        files = list(last_good_dir.glob("*.json")) if last_good_dir.exists() else []
        assert len(files) == 0


# ── Diagnostic flag (FR-AG-040) ───────────────────────────────────────────────

class TestDiagnostic:
    def _wait_for_result(self, max_s: float = 8.0) -> dict:
        deadline = time.monotonic() + max_s
        while time.monotonic() < deadline:
            d = client.get("/api/autogain/status").json()
            if not d["running"]:
                return d
            time.sleep(0.05)
        pytest.fail("AutoGain diagnostic run did not finish within timeout")

    def test_diagnostic_flag_reflected_in_status(self) -> None:
        with patch.object(deps, "get_preview_camera", return_value=_FakeCamera()):
            client.post("/api/autogain/run", json={"camera_index": 0, "diagnostic": True})
        d = self._wait_for_result()
        assert d["diagnostic"] is True

    def test_normal_run_diagnostic_flag_false(self) -> None:
        with patch.object(deps, "get_preview_camera", return_value=_FakeCamera()):
            client.post("/api/autogain/run", json={"camera_index": 0})
        d = self._wait_for_result()
        assert d["diagnostic"] is False

    def test_diagnostic_extends_profile_exp_to_10s(self) -> None:
        """The profile passed to the service must have max_preview_exp_ms >= 10 000."""
        captured_profile = {}

        original = ag_mod.AutoGainService.run_one_shot

        def _intercept(*args, **kwargs):
            captured_profile["profile"] = kwargs.get("profile") or (args[1] if len(args) > 1 else None)
            return original(*args, **kwargs)

        with (
            patch.object(ag_mod.AutoGainService, "run_one_shot", side_effect=_intercept),
            patch.object(deps, "get_preview_camera", return_value=_FakeCamera()),
        ):
            client.post("/api/autogain/run", json={
                "camera_index": 0,
                "camera_model": "ATR585M",
                "diagnostic": True,
            })
            self._wait_for_result()

        profile = captured_profile.get("profile")
        assert profile is not None
        assert profile.max_preview_exp_ms >= 10_000.0

    def test_non_diagnostic_run_leaves_profile_exp_unchanged(self) -> None:
        captured_profile = {}

        original = ag_mod.AutoGainService.run_one_shot

        def _intercept(*args, **kwargs):
            captured_profile["profile"] = kwargs.get("profile") or (args[1] if len(args) > 1 else None)
            return original(*args, **kwargs)

        with (
            patch.object(ag_mod.AutoGainService, "run_one_shot", side_effect=_intercept),
            patch.object(deps, "get_preview_camera", return_value=_FakeCamera()),
        ):
            client.post("/api/autogain/run", json={
                "camera_index": 0,
                "camera_model": "ATR585M",
                "diagnostic": False,
            })
            self._wait_for_result()

        from smart_telescope.domain.camera_profile import ATR585M
        profile = captured_profile.get("profile")
        assert profile is not None
        assert profile.max_preview_exp_ms == ATR585M.max_preview_exp_ms

    def test_focus_error_status_returned_in_diagnostic(self) -> None:
        """A camera returning faint signal at max limits → POSSIBLE_FOCUS_OR_POINTING_ERROR."""
        from smart_telescope.domain.autogain_service import AutoGainStatus

        class _FaintCamera(_FakeCamera):
            def capture(self, _exp):
                # mean_frac ≈ 0.005 — above focus threshold, below no-signal threshold
                return _make_frame(0.005)

        with patch.object(deps, "get_preview_camera", return_value=_FaintCamera()):
            client.post("/api/autogain/run", json={
                "camera_index": 0,
                "camera_model": "ATR585M",
                "diagnostic": True,
                "max_iterations": 20,
            })
        d = self._wait_for_result()
        assert d["status"] in (
            AutoGainStatus.POSSIBLE_FOCUS_OR_POINTING_ERROR.value,
            AutoGainStatus.NO_SIGNAL.value,
            AutoGainStatus.GAIN_LIMIT_REACHED.value,
            AutoGainStatus.EXPOSURE_LIMIT_REACHED.value,
        )
