"""Backend spreadsheet-grid contract builder.

The result is structured data, not HTML.  It lets a future UI render a grid
while the backend remains responsible for roster, binding, and score rules.
"""

from __future__ import annotations

from typing import Any

from grading.algorithms.practical_grid import build_component_columns


def build_grid_contract(
    *,
    assessment: Any,
    roster_rows: list[dict[str, Any]],
    components: list[Any],
    draft_rows: dict[str, dict[str, Any]] | None = None,
    submitted_rows: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    component_columns = build_component_columns(components)
    mode = "component" if component_columns else "simple"
    rows = []
    for row in roster_rows:
        student_id = row["student_id"]
        rows.append(
            {
                **row,
                "draft": (draft_rows or {}).get(student_id),
                "submitted": (submitted_rows or {}).get(student_id),
                "locked": student_id in (submitted_rows or {}),
            }
        )
    return {
        "assessment": {
            "assessment_id": str(assessment.id),
            "title": assessment.title,
            "max_score": str(assessment.max_score),
            "cohort_id": str(assessment.cohort_id),
            "learning_area_id": str(assessment.learning_area_id),
            "curriculum_version_id": str(assessment.curriculum_version_id),
            "rubric_foundation_id": str(assessment.rubric_foundation_id),
            "mode": mode,
        },
        "columns": component_columns
        or [
            {
                "field": "raw_score",
                "name": "Score",
                "max_score": str(assessment.max_score),
                "is_required": True,
            },
            {"field": "remarks", "name": "Remarks", "is_required": False},
        ],
        "rows": rows,
        "validation": {
            "score_min": "0",
            "score_max": str(assessment.max_score),
            "requires_step_up_for_submit": True,
        },
    }
