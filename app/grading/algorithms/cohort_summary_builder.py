"""Build cohort and learning-area completion summaries."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any


def completion_percentage(*, submitted_count: int, expected_count: int) -> Decimal:
    if expected_count <= 0:
        return Decimal("0.00")
    ratio = Decimal(submitted_count) / Decimal(expected_count)
    return (ratio * Decimal("100")).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )


def build_cohort_summary(
    *,
    assessment: Any,
    expected_count: int,
    submitted_count: int,
    missing_count: int,
    component_summary: dict[str, Any],
    status: str,
) -> dict[str, Any]:
    return {
        "tenant_id": str(assessment.tenant_id),
        "assessment_id": str(assessment.id),
        "cohort_id": str(assessment.cohort_id),
        "learning_area_id": str(assessment.learning_area_id),
        "expected_learner_count": expected_count,
        "submitted_learner_count": submitted_count,
        "missing_learner_count": missing_count,
        "completion_percentage": str(
            completion_percentage(
                submitted_count=submitted_count,
                expected_count=expected_count,
            )
        ),
        "component_summary": component_summary,
        "compilation_status": status,
    }
