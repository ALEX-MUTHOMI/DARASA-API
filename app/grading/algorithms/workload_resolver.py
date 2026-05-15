"""Workload result shaping for teacher-facing grading work."""

from __future__ import annotations

from typing import Any


def build_work_item(assessment: Any) -> dict[str, str]:
    return {
        "assessment_id": str(assessment.id),
        "title": assessment.title,
        "cohort_id": str(assessment.cohort_id),
        "cohort_name": assessment.cohort.name,
        "learning_area_id": str(assessment.learning_area_id),
        "learning_area_name": assessment.learning_area.name,
        "academic_year_id": str(assessment.academic_year_id),
        "term_id": str(assessment.term_id),
        "curriculum_version_id": str(assessment.curriculum_version_id),
    }
