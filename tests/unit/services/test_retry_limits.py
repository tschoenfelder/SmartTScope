"""M7-012 / SAFE-004 — Verify retry limits in all service loops.

Checks that no service loop runs indefinitely without a user-facing exit:
- AutoGainService: max_iterations parameter (default 12, API cap 30)
- AutofocusService: max_samples parameter (default 20)
- PlateSolveService: max_retries parameter (default 5)
- Collimation sub-services: constructor params (_max_steps, _max_iter, _max_frames)
"""

from __future__ import annotations

import inspect

import pytest


# ── AutoGainService ───────────────────────────────────────────────────────────

def test_autogain_service_has_max_iterations_param():
    from smart_telescope.domain.autogain_service import AutoGainService
    sig = inspect.signature(AutoGainService.run_one_shot)
    assert "max_iterations" in sig.parameters
    assert sig.parameters["max_iterations"].default == 12


def test_autogain_loop_respects_max_iterations():
    """AutoGainService exits after max_iterations even if target is never reached."""
    from unittest.mock import MagicMock
    import numpy as np
    from smart_telescope.domain.autogain import AutoGainMode
    from smart_telescope.domain.autogain_service import AutoGainService, AutoGainStatus
    from smart_telescope.domain.camera_profile import ATR585M
    from smart_telescope.domain.frame import FitsFrame
    from smart_telescope.ports.camera import CameraPort

    call_count = [0]

    class _CountingCam(CameraPort):
        def capture(self, _s):
            call_count[0] += 1
            frame = MagicMock(spec=FitsFrame)
            frame.pixels = np.zeros((64, 64), dtype=np.float32)
            return frame
        def connect(self): return True
        def disconnect(self): pass
        def get_exposure_ms(self): return 100.0
        def set_exposure_ms(self, ms): pass
        def get_gain(self): return 100
        def set_gain(self, g): pass
        def get_black_level(self): return 0
        def set_black_level(self, l): pass
        def get_conversion_gain(self): from smart_telescope.domain.camera_capabilities import ConversionGain; return ConversionGain.LCG
        def set_conversion_gain(self, m): pass
        def get_bit_depth(self): return 16
        def get_temperature(self): return None
        def get_capabilities(self): return MagicMock()
        def get_serial_number(self): return "TEST"
        def get_logical_name(self): return "TestCamera"

    result = AutoGainService.run_one_shot(
        _CountingCam(), ATR585M, max_iterations=3
    )
    assert call_count[0] <= 3
    assert result.status is not None  # always returns a result


# ── AutofocusService ──────────────────────────────────────────────────────────

def test_autofocus_service_has_max_samples_param():
    from smart_telescope.services.autofocus_service import AutofocusService
    sig = inspect.signature(AutofocusService.__init__)
    assert "max_samples" in sig.parameters
    assert sig.parameters["max_samples"].default == 20


def test_autofocus_exits_at_max_samples():
    """AutofocusService stops accepting frames once max_samples is reached."""
    import numpy as np
    from smart_telescope.services.autofocus_service import AutofocusService

    svc = AutofocusService(max_samples=3)
    frame = np.zeros((64, 64), dtype=np.float32)
    frame[32, 32] = 50000.0

    for _ in range(3):
        rec = svc.analyze(frame, current_position=0)

    # Next call must return autofocus_finished=True (safety cap triggered)
    final = svc.analyze(frame, current_position=0)
    assert final.autofocus_finished is True


# ── PlateSolveService ─────────────────────────────────────────────────────────

def test_plate_solve_service_has_max_retries_param():
    from smart_telescope.services.plate_solve_service import PlateSolveService
    sig = inspect.signature(PlateSolveService.__init__)
    assert "max_retries" in sig.parameters
    assert sig.parameters["max_retries"].default == 5


def test_plate_solve_raises_after_max_retries():
    """PlateSolveService raises PlateSolveError when max_retries is exceeded."""
    from unittest.mock import MagicMock
    import numpy as np
    from smart_telescope.adapters.astap.solver import AstapSolver
    from smart_telescope.domain.frame import FitsFrame
    from smart_telescope.ports.solver import SolveResult
    from smart_telescope.services.plate_solve_service import PlateSolveError, PlateSolveService

    solver = MagicMock(spec=AstapSolver)
    solver.solve.return_value = SolveResult(success=False, error="no match")
    frame = FitsFrame(pixels=np.zeros((64, 64), dtype=np.float32), header={}, exposure_seconds=1.0)

    svc = PlateSolveService(solver, max_retries=2)
    svc.mark_autogain_complete()

    svc.solve(frame, pixel_scale_hint=0.295)
    svc.solve(frame, pixel_scale_hint=0.295)

    with pytest.raises(PlateSolveError, match="retry limit"):
        svc.solve(frame, pixel_scale_hint=0.295)


# ── Collimation sub-services ──────────────────────────────────────────────────

def test_collimation_defocus_controller_has_max_steps():
    from smart_telescope.services.collimation.defocus_controller import DefocusController
    sig = inspect.signature(DefocusController.__init__)
    assert "max_steps" in sig.parameters


def test_collimation_mount_centering_has_max_iter():
    from smart_telescope.services.collimation.mount_centering import PulseCenterer
    sig = inspect.signature(PulseCenterer.__init__)
    assert "max_iterations" in sig.parameters


def test_collimation_live_guidance_has_max_frames():
    from smart_telescope.services.collimation.live_guidance import LiveGuidanceMonitor
    sig = inspect.signature(LiveGuidanceMonitor.__init__)
    assert "max_frames" in sig.parameters
