from __future__ import annotations

from decimal import Decimal

import pytest
from django.utils import timezone

from grading.models import Assessment, CompilationRun
from grading.services import (
    build_grade_record,
    build_submission_batch,
    compute_assessment_readiness,
    create_correction_request,
)


pytestmark = [pytest.mark.django_db, pytest.mark.phase6, pytest.mark.grading]


def _record(school, assessment, teacher_user, teacher_assignment, student):
    batch = build_submission_batch(
        tenant=school,
        actor=teacher_user,
        assessment=assessment,
        teacher_assignment=teacher_assignment,
        idempotency_key=f"phase6e-readiness-{student.id}",
    )
    return build_grade_record(
        tenant=school,
        actor=teacher_user,
        assessment=assessment,
        submission_batch=batch,
        student=student,
        raw_score=Decimal("80.00"),
    )


def _codes(readiness):
    return {item["code"] for item in readiness["blockers"]}


def test_pending_correction_blocks_report_readiness(
    school,
    assessment,
    teacher_user,
    teacher_assignment,
    principal_user,
    enrolled_student,
):
    record = _record(
        school,
        assessment,
        teacher_user,
        teacher_assignment,
        enrolled_student,
    )
    CompilationRun.objects.create(
        tenant=school,
        assessment=assessment,
        requested_by=principal_user,
        status=CompilationRun.Status.COMPLETE,
        expected_learner_count=1,
        submitted_learner_count=1,
        missing_learner_count=0,
        compiled_at=timezone.now(),
    )
    create_correction_request(
        actor=teacher_user,
        tenant=school,
        grade_record_id=record.id,
        payload={"reason": "Pending correction.", "proposed_raw_score": "81.00"},
    )

    readiness = compute_assessment_readiness(
        actor=principal_user,
        tenant=school,
        assessment_id=assessment.id,
    )

    assert not readiness["report_ready"]
    assert "correction_pending" in _codes(readiness)


def test_schema_required_internal_assessment_blocks_readiness_when_missing(
    school,
    assessment,
    teacher_user,
    teacher_assignment,
    principal_user,
    enrolled_student,
):
    Assessment.objects.filter(id=assessment.id).update(
        assessment_type=Assessment.AssessmentType.CAT,
    )
    assessment.refresh_from_db()
    _record(school, assessment, teacher_user, teacher_assignment, enrolled_student)
    CompilationRun.objects.create(
        tenant=school,
        assessment=assessment,
        requested_by=principal_user,
        status=CompilationRun.Status.COMPLETE,
        expected_learner_count=1,
        submitted_learner_count=1,
        missing_learner_count=0,
        compiled_at=timezone.now(),
    )

    readiness = compute_assessment_readiness(
        actor=principal_user,
        tenant=school,
        assessment_id=assessment.id,
    )

    assert "school_schema_missing" in _codes(readiness)
    assert not readiness["report_ready"]
