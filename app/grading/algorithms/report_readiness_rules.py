from __future__ import annotations

from typing import Any

from grading.algorithms.readiness_blockers import (
    ReadinessBlocker,
    blocker_dicts,
)
from grading.algorithms.readiness_status import determine_readiness_status


def build_report_readiness_summary(
    *,
    assessment_id: Any,
    cohort_id: Any,
    learning_area_id: Any,
    curriculum_version_id: Any,
    compilation_run_id: Any | None,
    compilation_status: str | None,
    expected_learner_count: int,
    submitted_learner_count: int,
    missing_learner_count: int,
    blocker_items: list[ReadinessBlocker],
    has_submitted_batch: bool,
    has_draft: bool,
    pending_correction_count: int = 0,
) -> dict[str, Any]:
    status = determine_readiness_status(
        compilation_status=compilation_status,
        blockers=blocker_items,
        has_submitted_batch=has_submitted_batch,
        has_draft=has_draft,
    )
    return {
        "assessment_id": str(assessment_id),
        "cohort_id": str(cohort_id),
        "learning_area_id": str(learning_area_id),
        "curriculum_version_id": str(curriculum_version_id or ""),
        "compilation_run_id": str(compilation_run_id or ""),
        "compilation_status": compilation_status or "not_started",
        "readiness_status": status,
        "report_ready": status == "ready_for_reports",
        "expected_learner_count": expected_learner_count,
        "submitted_learner_count": submitted_learner_count,
        "missing_learner_count": missing_learner_count,
        "pending_correction_count": pending_correction_count,
        "has_draft": has_draft,
        "has_submitted_batch": has_submitted_batch,
        "blocker_count": len(
            [item for item in blocker_items if item.severity == "blocking"]
        ),
        "review_count": len(
            [item for item in blocker_items if item.severity != "blocking"]
        ),
        "blockers": blocker_dicts(blocker_items),
    }
