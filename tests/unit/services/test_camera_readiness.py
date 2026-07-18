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

    def test_filter_wheel_device_not_listed_as_unconfigured_camera(self):
        # Hardware 2026-07-17: the ToupTek wheel enumerates as "FILTERWHEEL"
        # and was reported "connected but not configured" — it IS configured,
        # just not a camera role.
        import smart_telescope.config as cfg
        from smart_telescope.config import FilterWheelSpec
        svc = CameraReadinessService(
            enumerate_fn=lambda: list(_ALL_DEVICES) + [_dev("FILTERWHEEL")],
        )
        with patch.object(cfg, "CAMERA_SPECS", _SPECS), \
             patch.object(cfg, "CAMERAS", {}), \
             patch.object(cfg, "FILTER_WHEEL", FilterWheelSpec(enabled=True)):
            svc.scan_now()
        snap = svc.snapshot()
        assert snap["unassigned"] == []
        assert snap["filter_wheel"] == {
            "configured": True, "detected": True, "display_name": "FILTERWHEEL",
            "position": None, "filter_name": None,
        }
        # Camera indices still refer to the full enumeration order.
        assert snap["roles"]["main"]["sdk_index"] == 0

    def test_configured_wheel_not_detected_is_reported(self):
        import smart_telescope.config as cfg
        from smart_telescope.config import FilterWheelSpec
        svc = CameraReadinessService(enumerate_fn=lambda: list(_ALL_DEVICES))
        with patch.object(cfg, "CAMERA_SPECS", _SPECS), \
             patch.object(cfg, "CAMERAS", {}), \
             patch.object(cfg, "FILTER_WHEEL", FilterWheelSpec(enabled=True)):
            svc.scan_now()
        snap = svc.snapshot()
        assert snap["filter_wheel"] == {
            "configured": True, "detected": False, "display_name": None,
            "position": None, "filter_name": None,
        }

    def test_no_wheel_configured_and_none_detected_gives_none(self):
        import smart_telescope.config as cfg
        from smart_telescope.config import FilterWheelSpec
        svc = CameraReadinessService(enumerate_fn=lambda: list(_ALL_DEVICES))
        with patch.object(cfg, "CAMERA_SPECS", _SPECS), \
             patch.object(cfg, "CAMERAS", {}), \
             patch.object(cfg, "FILTER_WHEEL", FilterWheelSpec(enabled=False)):
            svc.scan_now()
        assert svc.snapshot()["filter_wheel"] is None

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


class TestFilterInPlace:
    """M10-014: the wheel snapshot names the filter currently in place."""

    def _scan_with_wheel(self, wheel_provider, filters):
        import smart_telescope.config as cfg
        from smart_telescope.config import FilterWheelSpec
        svc = CameraReadinessService(
            enumerate_fn=lambda: list(_ALL_DEVICES) + [_dev("FILTERWHEEL")],
            wheel_provider=wheel_provider,
        )
        with patch.object(cfg, "CAMERA_SPECS", _SPECS), \
             patch.object(cfg, "CAMERAS", {}), \
             patch.object(cfg, "FILTER_WHEEL", FilterWheelSpec(enabled=True)), \
             patch.object(cfg, "FILTERS", filters):
            svc.scan_now()
        return svc.snapshot()["filter_wheel"]

    def test_named_slot_reports_filter_name(self):
        wheel = SimpleNamespace(get_position=lambda: 5)
        fw = self._scan_with_wheel(lambda: wheel, {5: "H_Alpha"})
        assert fw["position"] == 5
        assert fw["filter_name"] == "H_Alpha"

    def test_unnamed_slot_falls_back_to_slot_number(self):
        wheel = SimpleNamespace(get_position=lambda: 3)
        fw = self._scan_with_wheel(lambda: wheel, {1: "Luminance"})
        assert fw["position"] == 3
        assert fw["filter_name"] == "slot 3"

    def test_wheel_position_failure_is_tolerated(self):
        def boom():
            raise RuntimeError("Filter wheel not connected")
        wheel = SimpleNamespace(get_position=boom)
        fw = self._scan_with_wheel(lambda: wheel, {1: "Luminance"})
        assert fw["position"] is None
        assert fw["filter_name"] is None

    def test_unknown_position_reports_none(self):
        wheel = SimpleNamespace(get_position=lambda: None)
        fw = self._scan_with_wheel(lambda: wheel, {1: "Luminance"})
        assert fw["position"] is None
        assert fw["filter_name"] is None


class TestOpenLockSerialization:
    """M10-023: the scan must never run concurrently with a camera SDK open."""

    def test_scan_skips_without_blocking_when_lock_is_held(self):
        import threading
        import time as _time
        lock = threading.RLock()
        svc = CameraReadinessService(
            enumerate_fn=lambda: list(_ALL_DEVICES),
            open_lock=lock,
        )
        import smart_telescope.config as cfg
        # RLock allows the same thread to re-acquire — hold it from a
        # different thread to simulate real cross-thread contention with an
        # in-progress camera open (readiness runs on its own thread in prod).
        held = threading.Event()
        release = threading.Event()

        def _hold_lock():
            with lock:
                held.set()
                release.wait(timeout=5.0)

        holder = threading.Thread(target=_hold_lock, daemon=True)
        holder.start()
        held.wait(timeout=5.0)
        try:
            with patch.object(cfg, "CAMERA_SPECS", _SPECS), patch.object(cfg, "CAMERAS", {}):
                t0 = _time.monotonic()
                svc.scan_now()
                elapsed = _time.monotonic() - t0
        finally:
            release.set()
            holder.join(timeout=5.0)
        assert elapsed < 0.5, "scan_now() blocked instead of skipping"
        assert svc.snapshot()["scanned"] is False

    def test_scan_proceeds_normally_when_lock_is_free(self):
        import threading
        lock = threading.RLock()
        svc = CameraReadinessService(
            enumerate_fn=lambda: list(_ALL_DEVICES),
            open_lock=lock,
        )
        import smart_telescope.config as cfg
        with patch.object(cfg, "CAMERA_SPECS", _SPECS), patch.object(cfg, "CAMERAS", {}):
            svc.scan_now()
        snap = svc.snapshot()
        assert snap["scanned"] is True
        assert snap["roles"]["main"]["status"] == "DETECTED"

    def test_no_lock_injected_behaves_as_before(self):
        svc = CameraReadinessService(enumerate_fn=lambda: list(_ALL_DEVICES))
        import smart_telescope.config as cfg
        with patch.object(cfg, "CAMERA_SPECS", _SPECS), patch.object(cfg, "CAMERAS", {}):
            svc.scan_now()
        assert svc.snapshot()["scanned"] is True


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
