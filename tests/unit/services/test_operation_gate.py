"""Unit tests for OperationGateService / evaluate_all_gates (M8-003 / REQ-STATE-003)."""
import pytest
from smart_telescope.services.operation_gate import (
    GATED_OPERATIONS,
    GateResult,
    evaluate_all_gates,
)

# ── helpers ──────────────────────────────────────────────────────────────────

def _fully_ready(mount_state: str = "TRACKING") -> dict:
    return dict(
        adapter_connection="OPEN",
        adapter_health="OK",
        mount_operational_state=mount_state,
        onstep_time_location="VERIFIED",
        raspberry_time_trust="TRUSTED",
    )


def _closed() -> dict:
    return dict(
        adapter_connection="CLOSED",
        adapter_health="UNKNOWN",
        mount_operational_state="UNKNOWN",
        onstep_time_location="UNKNOWN",
        raspberry_time_trust="NOT_TRUSTED",
    )


def _open_but_stage1_not_run() -> dict:
    return dict(
        adapter_connection="OPEN",
        adapter_health="OK",
        mount_operational_state="UNPARKED",
        onstep_time_location="UNKNOWN",
        raspberry_time_trust="NOT_TRUSTED",
    )


# ── all 13 operations returned ───────────────────────────────────────────────


class TestGatedOperationsCoverage:
    def test_all_13_operations_present(self) -> None:
        results = evaluate_all_gates(**_fully_ready())
        for op in GATED_OPERATIONS:
            assert op in results, f"operation {op!r} missing from result"

    def test_result_values_are_gate_result_instances(self) -> None:
        results = evaluate_all_gates(**_fully_ready())
        for op, r in results.items():
            assert isinstance(r, GateResult), f"{op} result is not GateResult"

    def test_gate_result_has_required_fields(self) -> None:
        results = evaluate_all_gates(**_fully_ready())
        r = results["goto"]
        assert hasattr(r, "allowed")
        assert hasattr(r, "reason_code")
        assert hasattr(r, "human_message")
        assert hasattr(r, "required_user_action")
        assert hasattr(r, "blocking_states")

    def test_exactly_13_gated_operations(self) -> None:
        assert len(GATED_OPERATIONS) == 13


# ── camera-only operations always allowed ────────────────────────────────────


class TestCameraOnlyOperations:
    def test_camera_capture_allowed_when_adapter_closed(self) -> None:
        results = evaluate_all_gates(**_closed())
        assert results["camera_capture"].allowed is True

    def test_plate_solve_allowed_when_adapter_closed(self) -> None:
        results = evaluate_all_gates(**_closed())
        assert results["plate_solve"].allowed is True

    def test_collimation_preview_allowed_even_without_raspberry_trust(self) -> None:
        # DEC-009: camera-only collimation preview allowed without trusted Raspberry time
        params = _fully_ready()
        params["raspberry_time_trust"] = "NOT_TRUSTED"
        results = evaluate_all_gates(**params)
        assert results["collimation_preview"].allowed is True

    def test_collimation_preview_allowed_even_with_time_location_unverified(self) -> None:
        params = _open_but_stage1_not_run()
        results = evaluate_all_gates(**params)
        assert results["collimation_preview"].allowed is True


# ── partial-mount operations (adapter + health only) ─────────────────────────


class TestPartialMountOperations:
    def test_manual_mount_move_allowed_without_time_location_verification(self) -> None:
        params = _open_but_stage1_not_run()
        results = evaluate_all_gates(**params)
        assert results["manual_mount_move"].allowed is True

    def test_manual_mount_move_blocked_when_adapter_closed(self) -> None:
        results = evaluate_all_gates(**_closed())
        r = results["manual_mount_move"]
        assert r.allowed is False
        assert r.reason_code == "ADAPTER_DISCONNECTED"

    def test_autofocus_allowed_without_time_location_verification(self) -> None:
        params = _open_but_stage1_not_run()
        results = evaluate_all_gates(**params)
        assert results["autofocus"].allowed is True

    def test_autofocus_blocked_when_health_failed(self) -> None:
        params = _open_but_stage1_not_run()
        params["adapter_health"] = "FAILED"
        results = evaluate_all_gates(**params)
        r = results["autofocus"]
        assert r.allowed is False
        assert r.reason_code == "ADAPTER_HEALTH_FAILED"


# ── full Stage 1 operations ───────────────────────────────────────────────────


class TestStage1RequiredOperations:
    @pytest.mark.parametrize("op", [
        "tracking_enable", "goto", "bright_star_goto", "sync",
        "plate_solve_mount_correction",
        "collimation_slew_to_target", "collimation_mount_centering",
        "click_to_center",
    ])
    def test_allowed_when_fully_ready(self, op: str) -> None:
        results = evaluate_all_gates(**_fully_ready())
        assert results[op].allowed is True, f"{op} should be allowed when fully ready"

    @pytest.mark.parametrize("op", [
        "tracking_enable", "goto", "bright_star_goto", "sync",
        "plate_solve_mount_correction",
        "collimation_slew_to_target", "collimation_mount_centering",
        "click_to_center",
    ])
    def test_blocked_when_adapter_closed(self, op: str) -> None:
        results = evaluate_all_gates(**_closed())
        r = results[op]
        assert r.allowed is False
        assert r.reason_code == "ADAPTER_DISCONNECTED"

    @pytest.mark.parametrize("op", [
        "tracking_enable", "goto", "bright_star_goto", "sync",
        "plate_solve_mount_correction",
        "collimation_slew_to_target", "collimation_mount_centering",
        "click_to_center",
    ])
    def test_blocked_when_time_location_unverified(self, op: str) -> None:
        params = dict(
            adapter_connection="OPEN",
            adapter_health="OK",
            mount_operational_state="UNPARKED",
            onstep_time_location="UNVERIFIED",
            raspberry_time_trust="NOT_TRUSTED",
        )
        results = evaluate_all_gates(**params)
        r = results[op]
        assert r.allowed is False
        assert r.reason_code == "TIME_LOCATION_UNVERIFIED"

    @pytest.mark.parametrize("op", [
        "tracking_enable", "goto", "bright_star_goto", "sync",
        "plate_solve_mount_correction",
        "collimation_slew_to_target", "collimation_mount_centering",
        "click_to_center",
    ])
    def test_blocked_when_raspberry_time_not_trusted(self, op: str) -> None:
        params = dict(
            adapter_connection="OPEN",
            adapter_health="OK",
            mount_operational_state="UNPARKED",
            onstep_time_location="VERIFIED",
            raspberry_time_trust="NOT_TRUSTED",
        )
        results = evaluate_all_gates(**params)
        r = results[op]
        assert r.allowed is False
        assert r.reason_code == "RASPBERRY_TIME_UNTRUSTED"


# ── parked-state blocking ─────────────────────────────────────────────────────


class TestParkedStateBlocking:
    @pytest.mark.parametrize("op", ["goto", "bright_star_goto", "click_to_center"])
    def test_blocked_when_parked(self, op: str) -> None:
        results = evaluate_all_gates(**_fully_ready(mount_state="PARKED"))
        r = results[op]
        assert r.allowed is False
        assert r.reason_code == "MOUNT_PARKED"

    def test_tracking_enable_not_blocked_by_parked_state(self) -> None:
        # Tracking enable is needed to unpark, so parked state alone doesn't block it
        results = evaluate_all_gates(**_fully_ready(mount_state="PARKED"))
        assert results["tracking_enable"].allowed is True


# ── gate result content ───────────────────────────────────────────────────────


class TestGateResultContent:
    def test_allowed_result_has_no_reason_code(self) -> None:
        results = evaluate_all_gates(**_fully_ready())
        r = results["goto"]
        assert r.allowed is True
        assert r.reason_code is None
        assert r.human_message is None
        assert r.required_user_action is None
        assert r.blocking_states == []

    def test_blocked_result_has_human_message(self) -> None:
        results = evaluate_all_gates(**_closed())
        r = results["goto"]
        assert r.human_message is not None
        assert len(r.human_message) > 0

    def test_blocked_result_has_required_user_action(self) -> None:
        results = evaluate_all_gates(**_closed())
        r = results["goto"]
        assert r.required_user_action is not None

    def test_blocking_states_includes_relevant_state(self) -> None:
        results = evaluate_all_gates(**_closed())
        r = results["goto"]
        assert len(r.blocking_states) > 0

    def test_time_location_block_suggests_stage1(self) -> None:
        params = dict(
            adapter_connection="OPEN",
            adapter_health="OK",
            mount_operational_state="UNPARKED",
            onstep_time_location="UNVERIFIED",
            raspberry_time_trust="NOT_TRUSTED",
        )
        results = evaluate_all_gates(**params)
        r = results["goto"]
        assert r.required_user_action == "run_stage1"

    def test_adapter_disconnected_block_suggests_connect_all(self) -> None:
        results = evaluate_all_gates(**_closed())
        r = results["goto"]
        assert r.required_user_action == "run_connect_all"

    def test_parked_block_suggests_unpark(self) -> None:
        results = evaluate_all_gates(**_fully_ready(mount_state="PARKED"))
        r = results["goto"]
        assert r.required_user_action == "unpark_mount"


# ── priority ordering ─────────────────────────────────────────────────────────


class TestBlockingPriority:
    def test_adapter_disconnected_takes_priority_over_time_location(self) -> None:
        # Even if time/location is UNVERIFIED, disconnected takes priority
        params = dict(
            adapter_connection="CLOSED",
            adapter_health="FAILED",
            mount_operational_state="UNKNOWN",
            onstep_time_location="UNVERIFIED",
            raspberry_time_trust="NOT_TRUSTED",
        )
        results = evaluate_all_gates(**params)
        assert results["goto"].reason_code == "ADAPTER_DISCONNECTED"

    def test_health_failed_takes_priority_over_time_location(self) -> None:
        params = dict(
            adapter_connection="OPEN",
            adapter_health="FAILED",
            mount_operational_state="UNKNOWN",
            onstep_time_location="UNVERIFIED",
            raspberry_time_trust="NOT_TRUSTED",
        )
        results = evaluate_all_gates(**params)
        assert results["goto"].reason_code == "ADAPTER_HEALTH_FAILED"

    def test_time_location_takes_priority_over_raspberry_trust(self) -> None:
        params = dict(
            adapter_connection="OPEN",
            adapter_health="OK",
            mount_operational_state="UNPARKED",
            onstep_time_location="UNVERIFIED",
            raspberry_time_trust="NOT_TRUSTED",
        )
        results = evaluate_all_gates(**params)
        assert results["goto"].reason_code == "TIME_LOCATION_UNVERIFIED"

    def test_raspberry_trust_takes_priority_over_parked(self) -> None:
        # Trust is checked before parked state
        params = dict(
            adapter_connection="OPEN",
            adapter_health="OK",
            mount_operational_state="PARKED",
            onstep_time_location="VERIFIED",
            raspberry_time_trust="NOT_TRUSTED",
        )
        results = evaluate_all_gates(**params)
        assert results["goto"].reason_code == "RASPBERRY_TIME_UNTRUSTED"
