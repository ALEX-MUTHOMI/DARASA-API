"""Minimal Phase 6A write helpers.

These helpers are intentionally narrow.  Phase 6A validates the grading data
model; Phase 6B will add the full batch submission service and event emission.
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError

from academics.models import TeacherAssignment
from grading.models import Assessment, GradeRecord, GradeSubmissionBatch


def build_submission_batch(
    *,
    tenant: Any,
    actor: Any,
    assessment: Assessment,
    teacher_assignment: TeacherAssignment,
    idempotency_key: str,
    record_count: int = 0,
    status: str = GradeSubmissionBatch.Status.SUBMITTED,
) -> GradeSubmissionBatch:
    """Create a batch with server-derived tenant/teacher/assignment context."""

    if teacher_assignment.teacher_id != actor.id:
        raise ValidationError({"teacher_assignment": "Teacher assignment is invalid."})
    return GradeSubmissionBatch.objects.create(
        tenant=tenant,
        assessment=assessment,
        teacher=actor,
        teacher_assignment=teacher_assignment,
        cohort=assessment.cohort,
        learning_area=assessment.learning_area,
        idempotency_key=idempotency_key,
        record_count=record_count,
        status=status,
    )


def build_grade_record(
    *,
    tenant: Any,
    actor: Any,
    assessment: Assessment,
    submission_batch: GradeSubmissionBatch,
    student: Any,
    raw_score: Any,
    remarks: str = "",
) -> GradeRecord:
    """Create a grade record using authenticated actor, not client identity."""

    return GradeRecord.objects.create(
        tenant=tenant,
        assessment=assessment,
        submission_batch=submission_batch,
        student=student,
        raw_score=raw_score,
        remarks=remarks,
        submitted_by=actor,
    )
