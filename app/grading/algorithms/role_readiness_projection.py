from __future__ import annotations

from collections import Counter
from typing import Any


def build_readiness_projection(
    *,
    projection_type: str,
    assessment_readiness: list[dict[str, Any]],
) -> dict[str, Any]:
    statuses = Counter(item["readiness_status"] for item in assessment_readiness)
    blocker_counts = Counter(
        blocker["code"]
        for item in assessment_readiness
        for blocker in item.get("blockers", [])
        if blocker.get("severity") == "blocking"
    )
    return {
        "projection_type": projection_type,
        "assessment_count": len(assessment_readiness),
        "ready_for_reports": all(
            item.get("report_ready") for item in assessment_readiness
        )
        if assessment_readiness
        else False,
        "status_counts": dict(sorted(statuses.items())),
        "blocker_counts": dict(sorted(blocker_counts.items())),
        "assessments": assessment_readiness,
    }


def build_future_parent_readiness_projection() -> dict[str, Any]:
    return {
        "projection_type": "future_parent",
        "ready_for_release": False,
        "assessments": [],
        "blockers": [
            {
                "code": "guardian_release_model_missing",
                "severity": "blocking",
                "message": (
                    "Future parent readiness fails closed until approved release "
                    "data exists."
                ),
                "scope": "learner",
                "resource_id": "",
            }
        ],
    }
