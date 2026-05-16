"""Compile practical/component score facts without subject hardcoding."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError

from grading.algorithms.practical_grid import component_total
from grading.algorithms.score_bounds import validate_score_bounds


def build_component_summary(
    *,
    component_scores: dict[str, Any],
    components: list[Any],
    assessment_max_score: Decimal,
) -> dict[str, Any]:
    component_by_id = {str(component.id): component for component in components}
    summaries = []
    missing_required = []
    for component_id, component in component_by_id.items():
        raw_value = component_scores.get(component_id)
        if raw_value in [None, ""]:
            if component.is_required:
                missing_required.append(component_id)
            summaries.append(
                {
                    "component_id": component_id,
                    "score": None,
                    "max_score": str(component.max_score),
                    "is_required": component.is_required,
                    "rubric_foundation_id": (
                        str(component.rubric_foundation_id)
                        if component.rubric_foundation_id
                        else None
                    ),
                }
            )
            continue
        score = validate_score_bounds(score=raw_value, max_score=component.max_score)
        summaries.append(
            {
                "component_id": component_id,
                "score": str(score),
                "max_score": str(component.max_score),
                "is_required": component.is_required,
                "rubric_foundation_id": (
                    str(component.rubric_foundation_id)
                    if component.rubric_foundation_id
                    else None
                ),
            }
        )
    total = component_total(
        {
            key: value
            for key, value in component_scores.items()
            if key in component_by_id and value not in [None, ""]
        }
    )
    validate_score_bounds(score=total, max_score=assessment_max_score)
    return {
        "mode": "component" if components else "simple",
        "components": summaries,
        "component_total": str(total) if components else None,
        "missing_required_component_ids": missing_required,
    }


def detect_invalid_component_scores(
    *,
    grade_records: list[Any],
    components: list[Any],
    assessment_max_score: Decimal,
) -> list[dict[str, Any]]:
    invalid = []
    for record in grade_records:
        try:
            build_component_summary(
                component_scores=record.component_scores or {},
                components=components,
                assessment_max_score=assessment_max_score,
            )
        except ValidationError:
            invalid.append(
                {
                    "learner_id": str(record.student_id),
                    "code": "invalid_component_score",
                    "severity": "failed",
                }
            )
    return invalid
