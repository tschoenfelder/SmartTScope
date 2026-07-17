"""Tests for CameraReadinessService — M10-002 (parallel camera identification)."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from smart_telescope.config import CameraSpec
from smart_telescope.services.camera_readiness import CameraReadinessService


def _dev(name: str) -> SimpleNamespace:
    return SimpleNamespace(displayname=name, id=name)


_SPECS = {
    "main":  CameraSpec(role="main",  model="ATR585M"),
    "guide": CameraSpec(role="guide", model="GPCMOS02000KPA"),
    "oag":   CameraSpec(role="oag",   model="G3M678M"),
}

_ALL_DEVICES = [
    _dev("ToupTek ATR585M"),
    _dev("ToupTek GPCMOS02000KPA"),
    _dev("ToupTek G3M678M"),
]


def _scan(
    devices=None, specs=_SPECS, enumerate_fn=None, registry=None,
):
    import smart_telescope.config as cfg
    svc = CameraReadinessService(
        enumerate_fn=enumerate_fn or (lambda: list(devices or [])),
        registry_provider=(lambda: registry) if registry is not None else None,
    )
    with patch.object(cfg, "CAMERA_SPECS", specs), patch.object(cfg, "CAMERAS", {}):
        svc.scan_now()
    return svc.snapshot()


class TestIdentification:
    def test_all_configured_cameras_detected(self):
        snap = _scan(devices=_ALL_DEVICES)
        assert snap["sdk_available"] is True
        assert snap["scanned"] is True
        for role in ("main", "guide", "oag"):
            assert snap["roles"][role]["status"] == "DETECTED", role
        assert snap["roles"]["main"]["display_name"] == "ToupTek ATR585M"
        assert snap["unassigned"] == []

    def test_unplugged_camera_reported_missing_others_detected(self):
        # M10-002 acceptance: one camera unplugged → MISSING for that role,
        # everything else keeps working.
        snap = _scan(devices=_ALL_DEVICES[:2])  # no G3M678M
        assert snap["roles"]["main"]["status"] == "DETECTED"
        assert snap["roles"]["guide"]["status"] == "DETECTED"
        assert snap["roles"]["oag"]["status"] == "MISSING"
        assert snap["roles"]["oag"]["reason"]

    def test_disabled_role_reported_disabled(self):
        specs = dict(_SPECS)
        specs["oag"] = CameraSpec(role="oag", model="G3M678M", enabled=False)
        snap = _scan(devices=_ALL_DEVICES, specs=specs)
        assert snap["roles"]["oag"]["status"] == "DISABLED"

    def test_sdk_unavailable_marks_all_missing_without_raising(self):
        def boom():
            raise ImportError("no toupcam")
        snap = _scan(enumerate_fn=boom)
        assert snap["sdk_available"] is False
        assert all(e["status"] == "MISSING" for e in snap["roles"].values())
        assert all("SDK unavailable" in e["reason"] for e in snap["roles"].values())

    def test_connected_but_unconfigured_device_listed_unassigned(self):
        snap = _scan(devices=_ALL_DEVICES + [_dev("ToupTek MYSTERY123")])
        assert snap["unassigned"] == ["ToupTek MYSTERY123"]

    def test_optical_configuration_joined_from_registry(self):
        train = SimpleNamespace(
            optical_configuration=lambda: {"telescope": "c8", "focal_mm": 2032.0},
        )
        registry = SimpleNamespace(
            by_camera_role=lambda role: train if role == "main" else None,
        )
        snap = _scan(devices=_ALL_DEVICES, registry=registry)
        assert snap["roles"]["main"]["optical"] == {"telescope": "c8", "focal_mm": 2032.0}
        assert snap["roles"]["guide"]["optical"] is None

    def test_snapshot_before_first_scan_is_empty_but_valid(self):
        svc = CameraReadinessService(enumerate_fn=lambda: [])
        snap = svc.snapshot()
        assert snap["scanned"] is False
        assert snap["roles"] == {}

    def test_registry_provider_failure_is_tolerated(self):
        def bad_registry():
            raise RuntimeError("registry broken")
        import smart_telescope.config as cfg
        svc = CameraReadinessService(
            enumerate_fn=lambda: list(_ALL_DEVICES),
            registry_provider=bad_registry,
        )
        with patch.object(cfg, "CAMERA_SPECS", _SPECS), patch.object(cfg, "CAMERAS", {}):
            svc.scan_now()
        snap = svc.snapshot()
        assert snap["roles"]["main"]["status"] == "DETECTED"
        assert snap["roles"]["main"]["optical"] is None


class TestLifecycle:
    def test_start_stop_background_loop(self):
        svc = CameraReadinessService(enumerate_fn=lambda: list(_ALL_DEVICES))
        import smart_telescope.config as cfg
        with patch.object(cfg, "CAMERA_SPECS", _SPECS), patch.object(cfg, "CAMERAS", {}):
            svc.start(poll_interval=0.05)
            import time
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline and not svc.snapshot()["scanned"]:
                time.sleep(0.02)
        svc.stop()
        assert svc.snapshot()["scanned"] is True

    def test_start_is_idempotent(self):
        svc = CameraReadinessService(enumerate_fn=lambda: [])
        svc.start(poll_interval=60.0)
        thread1 = svc._thread
        svc.start(poll_interval=60.0)
        assert svc._thread is thread1
        svc.stop()
