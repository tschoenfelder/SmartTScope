"""Integration test for the full guided observing flow (Phase 1 acceptance test).

Drives ObservingService end to end against the project's real mock adapters
(adapters/mock/*, the same hand-rolled fakes used by test_vertical_slice.py —
not unittest.mock) through the entire BOOTSTRAP -> ... -> PARKED_SAFE sequence,
proving the FSM + engine wiring works together, not just each piece in isolation.
"""

from __future__ import annotations

import time
from dataclasses import replace

from smart_telescope.adapters.mock.camera import MockCamera
from smart_telescope.adapters.mock.focuser import MockFocuser
from smart_telescope.adapters.mock.mount import MockMount
from smart_telescope.adapters.mock.solver import MockSolver
from smart_telescope.adapters.mock.stacker import MockStacker
from smart_telescope.adapters.mock.storage import MockStorage
from smart_telescope.domain.observing_state import Intent, ObservingPhase
from smart_telescope.ports.mount import MountState
from smart_telescope.services.device_state import DeviceStateService
from smart_telescope.services.guide_measurement import CentroidConfig, GuideControllerConfig
from smart_telescope.services.guiding_service import GuidingService
from smart_telescope.services.hardware_coordinator import HardwareCommandCoordinator
from smart_telescope.services.observing_service import ObservingDeps, ObservingService


def _wait_idle(svc: ObservingService, deps: ObservingDeps, timeout: float = 15.0) -> dict:
    deadline = time.monotonic() + timeout
    snap = svc.snapshot(deps)
    while snap["busy"]:
        if time.monotonic() > deadline:
            raise TimeoutError(f"ObservingService did not finish; last detail={snap['detail']}")
        time.sleep(0.02)
        snap = svc.snapshot(deps)
    return snap


class TestFullObservingFlow:
    def test_bootstrap_through_parked_safe(self) -> None:
        mount = MockMount(initial_state=MountState.TRACKING)
        device_state = DeviceStateService()
        device_state.start(mount)
        device_state.poll_now()
        try:
            deps = ObservingDeps(
                camera=MockCamera(),
                mount=mount,
                focuser=MockFocuser(available=True),
                solver=MockSolver(),
                stacker=MockStacker(),
                storage=MockStorage(),
                coordinator=HardwareCommandCoordinator(),
                device_state=device_state,
                guiding_service=GuidingService.from_config(
                    primary_role="guide", allow_fallback=False, fallback_after_bad_frames=3,
                    max_frame_age_s=5.0, centroid_config=CentroidConfig(),
                    controller_config=GuideControllerConfig(), measure_only=True,
                ),
                observer_lat=50.0, observer_lon=8.5,
                ha_east_limit_h=-12.0, ha_west_limit_h=12.0,
            )
            svc = ObservingService()
            assert svc.snapshot(deps)["phase"] == ObservingPhase.WAIT_CONTEXT_CONFIRMATION.value

            snap = svc.handle_intent(Intent.CONFIRM_CONTEXT, deps)
            assert snap["phase"] == ObservingPhase.WAIT_HOME_CONFIRMATION.value

            svc.handle_intent(Intent.START_HOME, deps)
            snap = _wait_idle(svc, deps)
            assert snap["guards"]["g2_home_confirmed"] is True
            assert mount.get_state() == MountState.AT_HOME

            snap = svc.handle_intent(Intent.CONFIRM_HOME, deps)
            assert snap["phase"] == ObservingPhase.POLAR_ALIGN.value

            svc.handle_intent(Intent.START_POLAR_ALIGN, deps)
            snap = _wait_idle(svc, deps)
            assert snap["phase"] == ObservingPhase.POLAR_ALIGN.value
            assert "polar_align" in snap["detail"]
            # Polar-align geometry from arbitrary mock solve points isn't
            # deterministically within tolerance (that math is unit-tested in
            # test_polar_workflow.py/test_polar_alignment.py already) — force
            # the guard here so this test can exercise the rest of the chain.
            with svc._lock:
                svc._guards = replace(svc._guards, g3_polar_within_tolerance=True)

            snap = svc.handle_intent(Intent.ACCEPT_POLAR_ALIGN, deps)
            assert snap["phase"] == ObservingPhase.FOCUS_READYING.value

            svc.handle_intent(Intent.START_FOCUS, deps)
            snap = _wait_idle(svc, deps)
            assert snap["guards"]["g4_focus_sufficient"] is True

            snap = svc.handle_intent(Intent.ACCEPT_FOCUS, deps)
            assert snap["phase"] == ObservingPhase.TARGET_ACQUIRE.value

            svc.handle_intent(Intent.START_TARGET_ACQUIRE, deps)
            snap = _wait_idle(svc, deps)
            assert snap["guards"]["g5_target_centered"] is True

            snap = svc.handle_intent(Intent.ACCEPT_TARGET, deps)
            assert snap["phase"] == ObservingPhase.GUIDE_READYING.value

            snap = svc.handle_intent(Intent.SKIP_GUIDING, deps)
            assert snap["guards"]["g6_guiding_ok"] is True

            snap = svc.handle_intent(Intent.START_CAPTURE, deps)
            assert snap["phase"] == ObservingPhase.CAPTURE_ACTIVE.value
            snap = _wait_idle(svc, deps, timeout=30.0)
            assert "capture" in snap["detail"]

            snap = svc.handle_intent(Intent.STOP_SAFELY, deps)
            assert snap["phase"] == ObservingPhase.SAFE_STOPPING.value
            snap = _wait_idle(svc, deps)
            assert snap["phase"] == ObservingPhase.PARKED_SAFE.value
            assert snap["guards"]["g8_safe_stop_possible"] is True
            assert mount.get_state() == MountState.PARKED
        finally:
            device_state.stop()
