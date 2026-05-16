"""Tests for SessionReportBuilder / CollimationSessionReport — COL-122."""
from __future__ import annotations

import pytest

from smart_telescope.services.collimation.maskless_validator import ValidationReport
from smart_telescope.services.collimation.session_report import (
    CollimationSessionReport,
    SessionReportBuilder,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _validation(status: str, error_px: float = 1.0, warnings=None) -> ValidationReport:
    return ValidationReport(
        status=status,
        donut_error_px=error_px,
        donut_error_ratio=error_px / 100.0,
        is_collimated=(status == "complete"),
        confidence=0.9,
        warnings=warnings or [],
    )


def _complete_builder() -> SessionReportBuilder:
    b = SessionReportBuilder()
    b.set_optical_train("c8-celestron")
    b.set_camera("touptek-iag130m")
    b.set_selected_star("Arcturus")
    b.record_rough_start(timestamp=1000.0)
    b.record_rough_end(timestamp=1100.0)
    b.record_fine_start(timestamp=1100.0)
    b.record_fine_end(timestamp=1200.0)
    b.record_focus_status(initial_fwhm=5.0, final_fwhm=2.0)
    b.record_seeing(jitter_px=1.5)
    b.record_final_result(_validation("complete", error_px=1.5))
    return b


# ── CollimationSessionReport fields ──────────────────────────────────────────

class TestSessionReportFields:
    def test_build_returns_report(self):
        b = _complete_builder()
        r = b.build()
        assert isinstance(r, CollimationSessionReport)

    def test_telescope_profile_set(self):
        r = _complete_builder().build()
        assert r.telescope_profile == "c8-celestron"

    def test_camera_id_set(self):
        r = _complete_builder().build()
        assert r.camera_id == "touptek-iag130m"

    def test_selected_star_set(self):
        r = _complete_builder().build()
        assert r.selected_star == "Arcturus"

    def test_timing_fields_set(self):
        r = _complete_builder().build()
        assert r.rough_started_at == pytest.approx(1000.0)
        assert r.rough_finished_at == pytest.approx(1100.0)
        assert r.fine_started_at == pytest.approx(1100.0)
        assert r.fine_finished_at == pytest.approx(1200.0)

    def test_started_at_set_by_rough_start(self):
        r = _complete_builder().build()
        assert r.started_at == pytest.approx(1000.0)

    def test_focus_fields_set(self):
        r = _complete_builder().build()
        assert r.initial_focus_fwhm_px == pytest.approx(5.0)
        assert r.final_focus_fwhm_px == pytest.approx(2.0)

    def test_seeing_jitter_set(self):
        r = _complete_builder().build()
        assert r.seeing_jitter_px == pytest.approx(1.5)

    def test_donut_fields_from_validation(self):
        r = _complete_builder().build()
        assert r.final_donut_error_px == pytest.approx(1.5)
        assert r.final_donut_status == "complete"


# ── Overall status derivation ─────────────────────────────────────────────────

class TestOverallStatus:
    def test_complete_when_validation_complete(self):
        b = SessionReportBuilder()
        b.record_final_result(_validation("complete"))
        assert b.build().overall_status == "complete"

    def test_acceptable_when_validation_acceptable_with_warning(self):
        b = SessionReportBuilder()
        b.record_final_result(_validation("acceptable_with_warning"))
        assert b.build().overall_status == "acceptable"

    def test_seeing_limited_maps_to_seeing_limited(self):
        b = SessionReportBuilder()
        b.record_final_result(_validation("seeing_limited"))
        assert b.build().overall_status == "seeing_limited"

    def test_failed_when_validation_failed(self):
        b = SessionReportBuilder()
        b.record_final_result(_validation("failed"))
        assert b.build().overall_status == "failed"

    def test_in_progress_when_no_final_result(self):
        b = SessionReportBuilder()
        b.set_optical_train("c8")
        assert b.build().overall_status == "in_progress"

    def test_cancelled_when_mark_cancelled(self):
        b = SessionReportBuilder()
        b.mark_cancelled()
        assert b.build().overall_status == "cancelled"

    def test_cancelled_overrides_no_result(self):
        b = SessionReportBuilder()
        b.record_final_result(_validation("complete"))
        b.mark_cancelled()
        assert b.build().overall_status == "cancelled"


# ── Warnings aggregation ──────────────────────────────────────────────────────

class TestWarnings:
    def test_validation_warnings_propagated(self):
        b = SessionReportBuilder()
        b.record_final_result(_validation("failed", warnings=["too much error"]))
        r = b.build()
        assert "too much error" in r.warnings

    def test_no_warnings_when_clean(self):
        b = SessionReportBuilder()
        b.record_final_result(_validation("complete", warnings=[]))
        r = b.build()
        assert r.warnings == []

    def test_multiple_warnings_aggregated(self):
        b = SessionReportBuilder()
        b.record_final_result(_validation("failed", warnings=["w1", "w2"]))
        r = b.build()
        assert "w1" in r.warnings
        assert "w2" in r.warnings


# ── to_dict ───────────────────────────────────────────────────────────────────

class TestToDict:
    def test_returns_dict(self):
        r = _complete_builder().build()
        assert isinstance(r.to_dict(), dict)

    def test_dict_has_overall_status(self):
        r = _complete_builder().build()
        assert r.to_dict()["overall_status"] == "complete"

    def test_dict_has_telescope_profile(self):
        r = _complete_builder().build()
        assert r.to_dict()["telescope_profile"] == "c8-celestron"

    def test_dict_warnings_is_list(self):
        r = _complete_builder().build()
        assert isinstance(r.to_dict()["warnings"], list)


# ── to_text ───────────────────────────────────────────────────────────────────

class TestToText:
    def test_returns_string(self):
        r = _complete_builder().build()
        assert isinstance(r.to_text(), str)

    def test_text_contains_status(self):
        r = _complete_builder().build()
        assert "COMPLETE" in r.to_text()

    def test_text_contains_profile(self):
        r = _complete_builder().build()
        assert "c8-celestron" in r.to_text()

    def test_text_contains_fwhm(self):
        r = _complete_builder().build()
        text = r.to_text()
        assert "5.00" in text  # initial FWHM
        assert "2.00" in text  # final FWHM

    def test_text_contains_star_name(self):
        r = _complete_builder().build()
        assert "Arcturus" in r.to_text()


# ── Defaults (minimal builder) ────────────────────────────────────────────────

class TestMinimalBuilder:
    def test_can_build_with_no_data(self):
        b = SessionReportBuilder()
        r = b.build()
        assert r.overall_status == "in_progress"
        assert r.telescope_profile == ""
        assert r.camera_id == ""
        assert r.selected_star is None
        assert r.final_donut_error_px is None
