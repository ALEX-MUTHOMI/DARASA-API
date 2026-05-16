"""Shape canonical compilation facts for role-specific backend views."""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError


SUPPORTED_PROJECTIONS = frozenset(
    {
        "teacher",
        "hod",
        "deputy_head_academics",
        "principal",
        "future_parent",
    }
)


def build_role_projection(
    *,
    projection_type: str,
    cohort_summaries: list[Any],
    learner_snapshots: list[Any] | None = None,
) -> dict[str, Any]:
    if projection_type not in SUPPORTED_PROJECTIONS:
        raise ValidationError({"projection": "Projection type is invalid."})
    summaries = [
        {
            "assessment_id": str(summary.assessment_id),
            "cohort_id": str(summary.cohort_id),
            "learning_area_id": str(summary.learning_area_id),
            "status": summary.status,
            "expected_learner_count": summary.expected_learner_count,
            "submitted_learner_count": summary.submitted_learner_count,
            "missing_learner_count": summary.missing_learner_count,
            "completion_percentage": str(summary.completion_percentage),
        }
        for summary in cohort_summaries
    ]
    payload: dict[str, Any] = {
        "projection_type": projection_type,
        "summaries": summaries,
    }
    if projection_type == "future_parent":
        payload["learner_snapshots"] = [
            {
                "assessment_id": str(snapshot.assessment_id),
                "learner_id": str(snapshot.student_id),
                "status": snapshot.status,
                "score_summary": snapshot.score_summary,
                "component_summary": snapshot.component_summary,
                "cbe_band_status": snapshot.cbe_band_status,
            }
            for snapshot in (learner_snapshots or [])
        ]
    return payload
