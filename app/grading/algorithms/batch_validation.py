"""Final grade batch validation for spreadsheet payloads."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from django.core.exceptions import ValidationError

from grading.algorithms.practical_grid import component_total
from grading.algorithms.score_bounds import validate_score_bounds


def _decimal(value: Any, field: str) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError({field: "Score must be numeric."}) from exc


def validate_grade_rows(
    *,
    rows: list[dict[str, Any]],
    roster_student_ids: set[str],
    max_score: Decimal,
    components: list[Any],
    require_complete: bool,
) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        raise ValidationError({"rows": "Rows must be a list."})
    seen: set[str] = set()
    normalized = []
    component_by_id = {str(component.id): component for component in components}
    for row in rows:
        student_id = str(row.get("student_id", "")).strip()
        if not student_id or student_id not in roster_student_ids:
            raise ValidationError({"student_id": "Submitted learner is invalid."})
        if student_id in seen:
            raise ValidationError({"student_id": "Duplicate learner row."})
        seen.add(student_id)
        component_scores = row.get("component_scores") or {}
        if component_by_id:
            if not isinstance(component_scores, dict):
                raise ValidationError(
                    {"component_scores": "Component scores must be an object."}
                )
            for component_id, component in component_by_id.items():
                raw_value = component_scores.get(component_id)
                if raw_value in [None, ""]:
                    if component.is_required and require_complete:
                        raise ValidationError(
                            {"component_scores": "Required component score missing."}
                        )
                    continue
                score = _decimal(raw_value, "component_scores")
                validate_score_bounds(score=score, max_score=component.max_score)
            total = component_total(
                {
                    key: value
                    for key, value in component_scores.items()
                    if value not in [None, ""]
                }
            )
            validate_score_bounds(score=total, max_score=max_score)
            raw_score = total if component_scores else None
        else:
            raw_value = row.get("raw_score")
            if raw_value in [None, ""]:
                if require_complete:
                    raise ValidationError({"raw_score": "Score is required."})
                raw_score = None
            else:
                raw_score = _decimal(raw_value, "raw_score")
                validate_score_bounds(score=raw_score, max_score=max_score)
        normalized.append(
            {
                "student_id": student_id,
                "raw_score": raw_score,
                "component_scores": component_scores,
                "remarks": str(row.get("remarks", "")),
            }
        )
    if require_complete and not normalized:
        raise ValidationError({"rows": "At least one grade row is required."})
    return normalized
