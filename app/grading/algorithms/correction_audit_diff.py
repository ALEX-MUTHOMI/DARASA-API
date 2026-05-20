"""PII-minimized audit diff helpers for grade correction application."""

from __future__ import annotations

from typing import Any

from grading.algorithms.correction_hash import hash_grade_state


def correction_changed_fields(
    *,
    old_raw_score: Any,
    new_raw_score: Any,
    old_component_scores: dict[str, Any],
    new_component_scores: dict[str, Any],
    old_remarks: str,
    new_remarks: str,
) -> list[str]:
    fields = []
    if new_raw_score is not None and str(old_raw_score) != str(new_raw_score):
        fields.append("raw_score")
    if new_component_scores and old_component_scores != new_component_scores:
        fields.append("component_scores")
    if new_remarks and old_remarks != new_remarks:
        fields.append("remarks")
    return sorted(fields)


def correction_state_hash(
    *,
    grade_record_id: Any,
    raw_score: Any,
    component_scores: dict[str, Any],
    remarks: str,
    version: int,
) -> str:
    return hash_grade_state(
        {
            "grade_record_id": str(grade_record_id),
            "raw_score": str(raw_score),
            "component_scores": component_scores,
            "remarks_hash": hash_grade_state({"remarks": remarks}),
            "version": version,
        }
    )
