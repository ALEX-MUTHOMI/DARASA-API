from __future__ import annotations

from typing import Any

from grading.algorithms.learner_improvement_detector import detect_most_improved
from grading.algorithms.performance_ranking import rank_learners
from grading.algorithms.subject_weakness_detector import detect_weak_subjects


def build_role_analytics_projection(
    *,
    projection_type: str,
    learner_snapshots: list[dict[str, Any]],
    aggregates: list[dict[str, Any]],
    readiness_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    subject_aggregates = [
        item for item in aggregates if item.get("scope_type") == "subject"
    ]
    return {
        "projection_type": projection_type,
        "snapshot_count": len(learner_snapshots),
        "aggregate_count": len(aggregates),
        "readiness_summary": readiness_summary or {},
        "top_learners": rank_learners(learner_snapshots),
        "most_improved": detect_most_improved(current=learner_snapshots),
        "weak_subjects": detect_weak_subjects(subject_aggregates),
        "aggregates": aggregates,
    }


def build_future_parent_snapshot_projection() -> dict[str, Any]:
    return {
        "projection_type": "future_parent",
        "ready_for_release": False,
        "learner_snapshots": [],
        "blockers": [
            {
                "code": "guardian_release_model_missing",
                "severity": "blocking",
                "message": (
                    "Parent analytics fails closed until guardian links and "
                    "approved report release records exist."
                ),
            }
        ],
    }
