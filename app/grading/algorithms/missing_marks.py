"""Detect missing, duplicate, and out-of-roster grade records."""

from __future__ import annotations

from typing import Any


def detect_missing_marks(
    *,
    roster_student_ids: set[str],
    grade_records: list[Any],
    components: list[Any],
) -> list[dict[str, Any]]:
    findings = []
    seen: set[str] = set()
    duplicate_ids: set[str] = set()
    component_ids = [
        str(component.id)
        for component in components
        if component.is_required
    ]
    for record in grade_records:
        student_id = str(record.student_id)
        if student_id in seen:
            duplicate_ids.add(student_id)
        seen.add(student_id)
        if student_id not in roster_student_ids:
            findings.append(
                {
                    "learner_id": student_id,
                    "missing_fields": [],
                    "severity": "failed",
                    "code": "student_outside_roster",
                }
            )
            continue
        missing_components = [
            component_id
            for component_id in component_ids
            if (record.component_scores or {}).get(component_id) in [None, ""]
        ]
        if missing_components:
            findings.append(
                {
                    "learner_id": student_id,
                    "missing_fields": missing_components,
                    "severity": "blocked",
                    "code": "missing_required_component",
                }
            )
    for student_id in sorted(roster_student_ids - seen):
        findings.append(
            {
                "learner_id": student_id,
                "missing_fields": ["raw_score"],
                "severity": "partial",
                "code": "missing_learner_mark",
            }
        )
    for student_id in sorted(duplicate_ids):
        findings.append(
            {
                "learner_id": student_id,
                "missing_fields": [],
                "severity": "failed",
                "code": "duplicate_grade_record",
            }
        )
    return sorted(findings, key=lambda item: (item["learner_id"], item["code"]))
