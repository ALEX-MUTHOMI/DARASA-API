"""Build learner-level compiled academic facts from one canonical input."""

from __future__ import annotations

from typing import Any

from grading.algorithms.cbe_band_mapper import map_cbe_band
from grading.algorithms.component_summary import build_component_summary
from grading.algorithms.score_summary import build_score_summary


def build_learner_snapshots(
    *,
    compilation_input: Any,
    missing_marks: list[dict[str, Any]],
    status: str,
    compiled_at: Any,
) -> list[dict[str, Any]]:
    assessment = compilation_input.assessment
    missing_by_student: dict[str, list[dict[str, Any]]] = {}
    for finding in missing_marks:
        missing_by_student.setdefault(finding["learner_id"], []).append(finding)
    snapshots = []
    for record in sorted(
        compilation_input.grade_records,
        key=lambda item: str(item.student_id),
    ):
        student_id = str(record.student_id)
        component_summary = build_component_summary(
            component_scores=record.component_scores or {},
            components=compilation_input.components,
            assessment_max_score=assessment.max_score,
        )
        band = map_cbe_band(rubric_foundation_id=assessment.rubric_foundation_id)
        snapshots.append(
            {
                "tenant_id": compilation_input.tenant_id,
                "learner_id": student_id,
                "assessment_id": str(assessment.id),
                "cohort_id": str(assessment.cohort_id),
                "learning_area_id": str(assessment.learning_area_id),
                "curriculum_version_id": str(assessment.curriculum_version_id),
                "rubric_foundation_id": str(assessment.rubric_foundation_id),
                "score_summary": build_score_summary(
                    grade_record=record,
                    assessment=assessment,
                ),
                "component_summary": component_summary,
                "missing_marks": missing_by_student.get(student_id, []),
                "cbe_band_status": band["status"],
                "compilation_status": status,
                "compiled_at": compiled_at.isoformat(),
                "source_batch_ids": compilation_input.source_batch_ids,
            }
        )
    return snapshots
