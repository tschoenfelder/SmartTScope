"""Unit tests for PerformanceTargets domain."""

from __future__ import annotations

from smart_telescope.domain.performance_targets import (
    TARGETS,
    PerformanceTarget,
    PerformanceTargets,
)


class TestPerformanceTargetFields:
    def test_targets_is_performance_targets_instance(self) -> None:
        assert isinstance(TARGETS, PerformanceTargets)

    def test_session_duration_positive(self) -> None:
        assert TARGETS.session_duration_hours.value > 0

    def test_preview_latency_positive(self) -> None:
        assert TARGETS.preview_latency_s.value > 0

    def test_stop_response_positive(self) -> None:
        assert TARGETS.stop_response_ms.value > 0

    def test_centering_accuracy_positive(self) -> None:
        assert TARGETS.centering_accuracy_arcsec.value > 0

    def test_plate_solve_success_between_0_and_100(self) -> None:
        pct = TARGETS.plate_solve_success_pct.value
        assert 0 < pct <= 100

    def test_pi_thermal_ceiling_positive(self) -> None:
        assert TARGETS.pi_thermal_ceiling_c.value > 0


class TestPerformanceTargetUnits:
    def test_all_targets_have_unit_strings(self) -> None:
        for name, pt in vars(TARGETS).items():
            assert isinstance(pt, PerformanceTarget), name
            assert isinstance(pt.unit, str) and pt.unit, f"{name}: empty unit"

    def test_all_targets_have_rationale(self) -> None:
        for name, pt in vars(TARGETS).items():
            assert isinstance(pt, PerformanceTarget), name
            assert isinstance(pt.rationale, str) and pt.rationale, f"{name}: empty rationale"


class TestPerformanceTargetSanity:
    def test_stop_response_under_one_second(self) -> None:
        assert TARGETS.stop_response_ms.value <= 1000, (
            "STOP must complete in ≤ 1 s per safety requirement"
        )

    def test_pi_thermal_ceiling_below_throttle_point(self) -> None:
        # Pi 5 throttles at 80°C; target must leave headroom
        assert TARGETS.pi_thermal_ceiling_c.value < 80

    def test_preview_latency_under_ten_seconds(self) -> None:
        assert TARGETS.preview_latency_s.value < 10
