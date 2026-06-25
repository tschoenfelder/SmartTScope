"""Unit tests for MountReadinessState derivation (M8-002 / REQ-STATE-002)."""
import pytest
from smart_telescope.domain.mount_readiness import MountReadinessState, derive_mount_readiness


class TestDeriveReadiness:
    def test_disconnected_when_adapter_closed(self) -> None:
        state = derive_mount_readiness(
            adapter_connection="CLOSED",
            adapter_health="OK",
            onstep_time_location="VERIFIED",
            raspberry_time_trust="TRUSTED",
        )
        assert state == MountReadinessState.DISCONNECTED

    def test_error_when_adapter_open_and_health_failed(self) -> None:
        state = derive_mount_readiness(
            adapter_connection="OPEN",
            adapter_health="FAILED",
            onstep_time_location="VERIFIED",
            raspberry_time_trust="TRUSTED",
        )
        assert state == MountReadinessState.ERROR

    def test_health_unknown_when_adapter_open_and_health_unknown(self) -> None:
        state = derive_mount_readiness(
            adapter_connection="OPEN",
            adapter_health="UNKNOWN",
            onstep_time_location="VERIFIED",
            raspberry_time_trust="TRUSTED",
        )
        assert state == MountReadinessState.CONNECTED_HEALTH_UNKNOWN

    def test_connected_restricted_when_time_location_unknown(self) -> None:
        # Stage 1 not yet run — time/location status not checked
        state = derive_mount_readiness(
            adapter_connection="OPEN",
            adapter_health="OK",
            onstep_time_location="UNKNOWN",
            raspberry_time_trust="NOT_TRUSTED",
        )
        assert state == MountReadinessState.CONNECTED_RESTRICTED

    def test_connected_time_location_unverified_when_unverified(self) -> None:
        # Stage 1 ran but user skipped push / verification failed
        state = derive_mount_readiness(
            adapter_connection="OPEN",
            adapter_health="OK",
            onstep_time_location="UNVERIFIED",
            raspberry_time_trust="NOT_TRUSTED",
        )
        assert state == MountReadinessState.CONNECTED_TIME_LOCATION_UNVERIFIED

    def test_connected_raspberry_time_untrusted_when_verified_but_not_trusted(self) -> None:
        # OnStep verified but Raspberry Pi time not trusted
        state = derive_mount_readiness(
            adapter_connection="OPEN",
            adapter_health="OK",
            onstep_time_location="VERIFIED",
            raspberry_time_trust="NOT_TRUSTED",
        )
        assert state == MountReadinessState.CONNECTED_RASPBERRY_TIME_UNTRUSTED

    def test_connected_ready_when_all_conditions_met(self) -> None:
        state = derive_mount_readiness(
            adapter_connection="OPEN",
            adapter_health="OK",
            onstep_time_location="VERIFIED",
            raspberry_time_trust="TRUSTED",
        )
        assert state == MountReadinessState.CONNECTED_READY

    def test_disconnected_takes_priority_over_health_failed(self) -> None:
        # Closed adapter — health/time states irrelevant
        state = derive_mount_readiness(
            adapter_connection="CLOSED",
            adapter_health="FAILED",
            onstep_time_location="UNVERIFIED",
            raspberry_time_trust="TRUSTED",
        )
        assert state == MountReadinessState.DISCONNECTED

    def test_error_takes_priority_over_time_location(self) -> None:
        state = derive_mount_readiness(
            adapter_connection="OPEN",
            adapter_health="FAILED",
            onstep_time_location="VERIFIED",
            raspberry_time_trust="TRUSTED",
        )
        assert state == MountReadinessState.ERROR
