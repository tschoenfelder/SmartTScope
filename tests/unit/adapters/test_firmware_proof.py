"""Tests for adapters/onstep/firmware_proof.py — proof file I/O and validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from smart_telescope.adapters.onstep.firmware_proof import (
    AXIS1_FALLBACK_TEST_ID,
    DUAL_PIER_TEST_ID,
    PROOF_SCHEMA,
    load_firmware_proof,
    validate_firmware_proof,
    write_firmware_proof,
)

_FIRMWARE = {"product": "OnStep", "version": "10.24i", "date": "2024-03-01"}


def _base_dual_pier_proof(**overrides: Any) -> dict[str, Any]:
    proof: dict[str, Any] = {
        "schema": PROOF_SCHEMA,
        "test_id": DUAL_PIER_TEST_ID,
        "result": "pass",
        "proven_pier_sides": ["east", "west"],
        "firmware_identity": {
            "product": _FIRMWARE["product"],
            "version": _FIRMWARE["version"],
            "date": _FIRMWARE["date"],
        },
        "west_limit_minutes": 15.0,
    }
    proof.update(overrides)
    return proof


def _base_axis1_proof(**overrides: Any) -> dict[str, Any]:
    proof: dict[str, Any] = {
        "schema": PROOF_SCHEMA,
        "test_id": AXIS1_FALLBACK_TEST_ID,
        "result": "pass",
        "pier_side": "east",
        "firmware_fallback_type": "axis1_max",
        "physically_safe_confirmed": True,
        "firmware_identity": {
            "product": _FIRMWARE["product"],
            "version": _FIRMWARE["version"],
            "date": _FIRMWARE["date"],
        },
        "west_limit_minutes": 15.0,
        "axis_limits": {"axis1_max": 90.0},
        "observer": {"lat": 50.336, "lon": 8.533},
        "auto_meridian_flip_enabled": False,
    }
    proof.update(overrides)
    return proof


# ── load_firmware_proof ────────────────────────────────────────────────────────

class TestLoadFirmwareProof:
    def test_loads_valid_json_file(self, tmp_path: Path) -> None:
        p = tmp_path / "proof.json"
        p.write_text(json.dumps({"schema": PROOF_SCHEMA}), encoding="utf-8")
        data = load_firmware_proof(p)
        assert data == {"schema": PROOF_SCHEMA}

    def test_returns_none_for_missing_file(self, tmp_path: Path) -> None:
        assert load_firmware_proof(tmp_path / "no_such.json") is None

    def test_returns_none_for_invalid_json(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.json"
        p.write_text("NOT JSON", encoding="utf-8")
        assert load_firmware_proof(p) is None

    def test_returns_none_for_json_array(self, tmp_path: Path) -> None:
        p = tmp_path / "list.json"
        p.write_text("[1, 2, 3]", encoding="utf-8")
        assert load_firmware_proof(p) is None


# ── write_firmware_proof ────────────────────────────────────────────────────────

class TestWriteFirmwareProof:
    def test_creates_file(self, tmp_path: Path) -> None:
        p = tmp_path / "proof.json"
        write_firmware_proof(p, {"test_id": "test"})
        assert p.exists()

    def test_written_file_is_valid_json(self, tmp_path: Path) -> None:
        p = tmp_path / "proof.json"
        write_firmware_proof(p, {"test_id": "test"})
        data = json.loads(p.read_text(encoding="utf-8"))
        assert isinstance(data, dict)

    def test_schema_field_injected(self, tmp_path: Path) -> None:
        p = tmp_path / "proof.json"
        write_firmware_proof(p, {})
        data = json.loads(p.read_text(encoding="utf-8"))
        assert data["schema"] == PROOF_SCHEMA

    def test_recorded_at_utc_injected(self, tmp_path: Path) -> None:
        p = tmp_path / "proof.json"
        write_firmware_proof(p, {})
        data = json.loads(p.read_text(encoding="utf-8"))
        assert "recorded_at_utc" in data

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        p = tmp_path / "nested" / "deep" / "proof.json"
        write_firmware_proof(p, {"x": 1})
        assert p.exists()

    def test_returns_path(self, tmp_path: Path) -> None:
        p = tmp_path / "proof.json"
        result = write_firmware_proof(p, {})
        assert result == p


# ── validate_firmware_proof ────────────────────────────────────────────────────

class TestValidateFirmwareProof:
    def _validate_dual(self, proof: dict[str, Any] | None, **kw: Any) -> dict[str, object]:
        return validate_firmware_proof(
            proof,
            firmware_identity=_FIRMWARE,
            dual_pier_enabled=True,
            west_limit_minutes=15.0,
            requested_west_stop_h=0.25,
            **kw,
        )

    def _validate_axis1(self, proof: dict[str, Any] | None, **kw: Any) -> dict[str, object]:
        return validate_firmware_proof(
            proof,
            firmware_identity=_FIRMWARE,
            dual_pier_enabled=False,
            west_limit_minutes=15.0,
            requested_west_stop_h=0.25,
            axis_limits={"axis1_max": 90.0},
            observer={"lat": 50.336, "lon": 8.533},
            auto_meridian_flip_enabled=False,
            **kw,
        )

    def test_none_proof_invalid(self) -> None:
        r = self._validate_dual(None)
        assert r["valid"] is False
        assert "firmware_safeguard_proof_missing" in r["reasons"]

    def test_wrong_schema_invalid(self) -> None:
        p = _base_dual_pier_proof(schema="wrong-schema-v99")
        r = self._validate_dual(p)
        assert "firmware_safeguard_proof_schema_mismatch" in r["reasons"]

    def test_wrong_test_id_invalid(self) -> None:
        p = _base_dual_pier_proof(test_id="totally_unknown_test")
        r = self._validate_dual(p)
        assert "firmware_safeguard_wrong_test" in r["reasons"]

    def test_result_not_pass_invalid(self) -> None:
        p = _base_dual_pier_proof(result="fail")
        r = self._validate_dual(p)
        assert "firmware_safeguard_test_not_passed" in r["reasons"]

    def test_dual_pier_missing_sides_invalid(self) -> None:
        p = _base_dual_pier_proof(proven_pier_sides=["east"])
        r = self._validate_dual(p)
        assert "firmware_safeguard_both_pier_sides_not_proven" in r["reasons"]

    def test_dual_pier_not_enabled_invalid(self) -> None:
        p = _base_dual_pier_proof()
        r = validate_firmware_proof(
            p,
            firmware_identity=_FIRMWARE,
            dual_pier_enabled=False,
            west_limit_minutes=15.0,
            requested_west_stop_h=0.25,
        )
        assert "dual_pier_west_ha_stop_not_enabled" in r["reasons"]

    def test_firmware_identity_mismatch_invalid(self) -> None:
        p = _base_dual_pier_proof()
        r = validate_firmware_proof(
            p,
            firmware_identity={"product": "OnStep", "version": "OLD", "date": "2020-01-01"},
            dual_pier_enabled=True,
            west_limit_minutes=15.0,
            requested_west_stop_h=0.25,
        )
        assert "firmware_identity_changed_since_proof" in r["reasons"]

    def test_west_limit_unreadable_invalid(self) -> None:
        p = _base_dual_pier_proof()
        r = validate_firmware_proof(
            p,
            firmware_identity=_FIRMWARE,
            dual_pier_enabled=True,
            west_limit_minutes=None,
            requested_west_stop_h=0.25,
        )
        assert "west_meridian_limit_unreadable" in r["reasons"]

    def test_west_limit_mismatch_invalid(self) -> None:
        p = _base_dual_pier_proof()
        r = validate_firmware_proof(
            p,
            firmware_identity=_FIRMWARE,
            dual_pier_enabled=True,
            west_limit_minutes=999.0,
            requested_west_stop_h=0.25,
        )
        assert "west_meridian_limit_no_longer_matches_policy" in r["reasons"]

    def test_valid_dual_pier_proof(self) -> None:
        r = self._validate_dual(_base_dual_pier_proof())
        assert r["valid"] is True
        assert r["reasons"] == []

    def test_axis1_pier_east_not_proven(self) -> None:
        p = _base_axis1_proof(pier_side="west")
        r = self._validate_axis1(p)
        assert "axis1_fallback_pier_east_not_proven" in r["reasons"]

    def test_axis1_fallback_type_mismatch(self) -> None:
        p = _base_axis1_proof(firmware_fallback_type="wrong")
        r = self._validate_axis1(p)
        assert "axis1_fallback_type_mismatch" in r["reasons"]

    def test_axis1_physical_safety_not_confirmed(self) -> None:
        p = _base_axis1_proof(physically_safe_confirmed=False)
        r = self._validate_axis1(p)
        assert "axis1_fallback_physical_safety_not_confirmed" in r["reasons"]

    def test_axis1_observer_changed(self) -> None:
        p = _base_axis1_proof(observer={"lat": 99.0, "lon": 99.0})
        r = self._validate_axis1(p)
        assert "observer_changed_since_proof" in r["reasons"]

    def test_axis1_auto_flip_state_changed(self) -> None:
        p = _base_axis1_proof(auto_meridian_flip_enabled=True)
        r = self._validate_axis1(p)
        assert "automatic_meridian_flip_state_changed_since_proof" in r["reasons"]

    def test_axis1_flip_state_unreadable(self) -> None:
        p = _base_axis1_proof()
        r = validate_firmware_proof(
            p,
            firmware_identity=_FIRMWARE,
            dual_pier_enabled=False,
            west_limit_minutes=15.0,
            requested_west_stop_h=0.25,
            axis_limits={"axis1_max": 90.0},
            observer={"lat": 50.336, "lon": 8.533},
            auto_meridian_flip_enabled=None,
        )
        assert "automatic_meridian_flip_state_unreadable" in r["reasons"]

    def test_valid_axis1_proof(self) -> None:
        r = self._validate_axis1(_base_axis1_proof())
        assert r["valid"] is True
        assert r["reasons"] == []
