"""Unit tests for milestones domain — MilestoneSummary and registries."""

from __future__ import annotations

import pytest

from smart_telescope.domain.milestones import (
    EVIDENCE_GAPS,
    MILESTONE_REGISTRY,
    RISK_REGISTRY,
    EvidenceGapItem,
    MilestoneSummary,
    RiskItem,
)

_PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


# ── MilestoneSummary.status ───────────────────────────────────────────────────


class TestMilestoneSummaryStatus:
    def test_green_when_all_open_are_hardware_blocked(self) -> None:
        m = MilestoneSummary(
            id="X", name="X", total=5, done=3,
            hardware_blocked=2, p0_open=0, p1_open=0,
        )
        assert m.status == "green"

    def test_green_when_fully_done(self) -> None:
        m = MilestoneSummary(
            id="X", name="X", total=4, done=4,
            hardware_blocked=0, p0_open=0, p1_open=0,
        )
        assert m.status == "green"

    def test_yellow_when_p1_open(self) -> None:
        m = MilestoneSummary(
            id="X", name="X", total=5, done=3,
            hardware_blocked=0, p0_open=0, p1_open=2,
        )
        assert m.status == "yellow"

    def test_yellow_when_only_p2_open_non_hardware(self) -> None:
        m = MilestoneSummary(
            id="X", name="X", total=5, done=3,
            hardware_blocked=1, p0_open=0, p1_open=0,
        )
        # 2 open, 1 hardware-blocked → 1 non-hardware open (P2/P3)
        assert m.status == "yellow"

    def test_red_when_p0_open(self) -> None:
        m = MilestoneSummary(
            id="X", name="X", total=5, done=3,
            hardware_blocked=0, p0_open=1, p1_open=0,
        )
        assert m.status == "red"

    def test_open_equals_total_minus_done(self) -> None:
        m = MilestoneSummary(
            id="X", name="X", total=10, done=7,
            hardware_blocked=0, p0_open=0, p1_open=0,
        )
        assert m.open == 3


# ── MILESTONE_REGISTRY ────────────────────────────────────────────────────────


class TestMilestoneRegistry:
    def test_registry_is_not_empty(self) -> None:
        assert len(MILESTONE_REGISTRY) > 0

    def test_all_ids_are_unique(self) -> None:
        ids = [m.id for m in MILESTONE_REGISTRY]
        assert len(ids) == len(set(ids))

    def test_done_never_exceeds_total(self) -> None:
        for m in MILESTONE_REGISTRY:
            assert m.done <= m.total, f"{m.id}: done={m.done} > total={m.total}"

    def test_hardware_blocked_never_exceeds_open(self) -> None:
        for m in MILESTONE_REGISTRY:
            assert m.hardware_blocked <= m.open, (
                f"{m.id}: hardware_blocked={m.hardware_blocked} > open={m.open}"
            )

    def test_status_values_are_valid(self) -> None:
        valid = {"green", "yellow", "red"}
        for m in MILESTONE_REGISTRY:
            assert m.status in valid, f"{m.id}: unexpected status {m.status!r}"


# ── RISK_REGISTRY ─────────────────────────────────────────────────────────────


class TestRiskRegistry:
    def test_registry_is_not_empty(self) -> None:
        assert len(RISK_REGISTRY) > 0

    def test_at_most_ten_risks(self) -> None:
        assert len(RISK_REGISTRY) <= 10

    def test_all_risks_are_p0_or_p1(self) -> None:
        for r in RISK_REGISTRY:
            assert r.priority in ("P0", "P1"), (
                f"{r.id}: unexpected priority {r.priority!r}"
            )

    def test_p0_comes_before_p1(self) -> None:
        priorities = [r.priority for r in RISK_REGISTRY]
        # No P1 should appear before any P0
        last_p0 = max(
            (i for i, p in enumerate(priorities) if p == "P0"), default=-1
        )
        first_p1 = min(
            (i for i, p in enumerate(priorities) if p == "P1"), default=len(priorities)
        )
        assert last_p0 < first_p1 or first_p1 == len(priorities), (
            "P1 entry appears before P0 entry in RISK_REGISTRY"
        )

    def test_all_risk_ids_are_unique(self) -> None:
        ids = [r.id for r in RISK_REGISTRY]
        assert len(ids) == len(set(ids))


# ── EVIDENCE_GAPS ─────────────────────────────────────────────────────────────


class TestEvidenceGaps:
    def test_registry_is_not_empty(self) -> None:
        assert len(EVIDENCE_GAPS) > 0

    def test_all_items_are_p0_or_p1(self) -> None:
        for g in EVIDENCE_GAPS:
            assert g.priority in ("P0", "P1"), (
                f"{g.id}: unexpected priority {g.priority!r}"
            )

    def test_all_ids_are_unique(self) -> None:
        ids = [g.id for g in EVIDENCE_GAPS]
        assert len(ids) == len(set(ids))

    def test_all_items_have_non_empty_mock_tested_by(self) -> None:
        for g in EVIDENCE_GAPS:
            assert isinstance(g.mock_tested_by, str) and g.mock_tested_by, (
                f"{g.id}: empty mock_tested_by"
            )

    def test_all_items_have_non_empty_hardware_needed(self) -> None:
        for g in EVIDENCE_GAPS:
            assert isinstance(g.hardware_needed, str) and g.hardware_needed, (
                f"{g.id}: empty hardware_needed"
            )

    def test_p0_items_come_before_p1(self) -> None:
        priorities = [g.priority for g in EVIDENCE_GAPS]
        last_p0 = max(
            (i for i, p in enumerate(priorities) if p == "P0"), default=-1
        )
        first_p1 = min(
            (i for i, p in enumerate(priorities) if p == "P1"), default=len(priorities)
        )
        assert last_p0 < first_p1 or first_p1 == len(priorities), (
            "P1 entry appears before P0 entry in EVIDENCE_GAPS"
        )
