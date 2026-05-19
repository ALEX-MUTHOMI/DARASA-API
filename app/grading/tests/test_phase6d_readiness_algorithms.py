from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from grading.algorithms.cct_readiness_guard import cct_readiness_blockers
from grading.algorithms.component_readiness import component_readiness_blockers
from grading.algorithms.readiness_blockers import blocker
from grading.algorithms.readiness_status import (
    ReadinessStatus,
    determine_readiness_status,
)
from grading.algorithms.stale_compilation_detector import detect_stale_compilation


pytestmark = [pytest.mark.phase6, pytest.mark.grading]


def test_complete_compilation_without_blockers_is_report_ready():
    assert (
        determine_readiness_status(
            compilation_status="complete",
            blockers=[],
            has_submitted_batch=True,
            has_draft=False,
        )
        == ReadinessStatus.READY_FOR_REPORTS
    )


def test_missing_marks_components_failed_stale_and_corrections_block_readiness():
    assert determine_readiness_status(
        compilation_status="partial",
        blockers=[blocker(code="missing_marks", message="Missing marks")],
        has_submitted_batch=True,
        has_draft=False,
    ) == ReadinessStatus.PARTIAL
    assert determine_readiness_status(
        compilation_status="complete",
        blockers=[
            blocker(
                code="missing_required_component",
                message="Missing component",
            )
        ],
        has_submitted_batch=True,
        has_draft=False,
    ) == ReadinessStatus.BLOCKED
    assert determine_readiness_status(
        compilation_status="failed",
        blockers=[],
        has_submitted_batch=True,
        has_draft=False,
    ) == ReadinessStatus.FAILED
    assert determine_readiness_status(
        compilation_status="stale",
        blockers=[],
        has_submitted_batch=True,
        has_draft=False,
    ) == ReadinessStatus.STALE
    assert determine_readiness_status(
        compilation_status="complete",
        blockers=[blocker(code="correction_pending", message="Correction pending")],
        has_submitted_batch=True,
        has_draft=False,
    ) == ReadinessStatus.NEEDS_CORRECTION


def test_component_readiness_detects_missing_required_components():
    blockers = component_readiness_blockers(
        component_summary={"missing_required_component_count": 2}
    )

    assert [item.code for item in blockers] == ["missing_required_component"]


def test_stale_compilation_detector_is_deterministic():
    compiled_at = timezone.now()
    freshness = detect_stale_compilation(
        compilation_status="complete",
        compiled_at=compiled_at,
        latest_batch_submitted_at=compiled_at + timedelta(minutes=1),
    )

    assert freshness.is_stale
    assert freshness.reasons == ("submission_after_compilation",)


def test_cct_guard_flags_adoption_withdrawal_and_rollback_without_mutation():
    blockers = cct_readiness_blockers(
        assessment_is_bound=True,
        has_school_adoption=False,
        curriculum_version_withdrawn=True,
        rollback_plan_count=1,
        app_impact_plan_count=1,
    )

    assert {item.code for item in blockers} == {
        "cct_adoption_missing",
        "cct_withdrawal_review_required",
        "cct_rollback_review_required",
        "cct_app_impact_review_required",
    }
