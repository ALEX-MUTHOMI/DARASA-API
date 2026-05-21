from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0.00")


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def build_subject_line_payload(*, compiled_snapshot: Any) -> dict[str, Any]:
    assessment = compiled_snapshot.assessment
    score_summary = dict(compiled_snapshot.score_summary or {})
    return {
        "compiled_learner_snapshot_id": str(compiled_snapshot.id),
        "compilation_run_id": str(compiled_snapshot.compilation_run_id),
        "assessment_id": str(compiled_snapshot.assessment_id),
        "student_id": str(compiled_snapshot.student_id),
        "cohort_id": str(compiled_snapshot.cohort_id),
        "learning_area_id": str(compiled_snapshot.learning_area_id),
        "curriculum_version_id": str(compiled_snapshot.curriculum_version_id),
        "rubric_foundation_id": str(compiled_snapshot.rubric_foundation_id or ""),
        "school_grading_schema_version": (
            getattr(assessment, "school_grading_schema_version", "") or ""
        ),
        "score_summary": score_summary,
        "component_summary": dict(compiled_snapshot.component_summary or {}),
        "percentage": str(score_summary.get("percentage") or "0.00"),
        "raw_score": str(score_summary.get("raw_score") or "0.00"),
        "cbe_band_status": compiled_snapshot.cbe_band_status,
        "internal_band_label": getattr(assessment, "internal_band_label", "") or "",
        "internal_band_descriptor": (
            getattr(assessment, "internal_band_descriptor", "") or ""
        ),
        "status": compiled_snapshot.status,
    }


def build_learner_snapshot_payload(
    *,
    student_id: Any,
    subject_lines: list[dict[str, Any]],
    readiness_status: str,
) -> dict[str, Any]:
    percentages = [_decimal(item.get("percentage")) for item in subject_lines]
    raw_scores = [_decimal(item.get("raw_score")) for item in subject_lines]
    subject_count = len(subject_lines)
    average = (
        _quantize(sum(percentages) / Decimal(subject_count))
        if subject_count
        else Decimal("0.00")
    )
    schema_versions = {
        item["assessment_id"]: item["school_grading_schema_version"]
        for item in subject_lines
        if item.get("school_grading_schema_version")
    }
    return {
        "student_id": str(student_id),
        "subject_count": subject_count,
        "total_score": str(_quantize(sum(raw_scores))),
        "average_percentage": str(average),
        "source_compilation_run_ids": sorted(
            {item["compilation_run_id"] for item in subject_lines}
        ),
        "readiness_status": readiness_status,
        "schema_versions": schema_versions,
        "context_snapshot": {
            "assessment_ids": sorted({item["assessment_id"] for item in subject_lines}),
            "curriculum_version_ids": sorted(
                {item["curriculum_version_id"] for item in subject_lines}
            ),
            "learning_area_ids": sorted(
                {item["learning_area_id"] for item in subject_lines}
            ),
        },
        "correction_audit_state": {"resolved": True},
    }
