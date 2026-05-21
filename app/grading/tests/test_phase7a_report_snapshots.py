from __future__ import annotations

from decimal import Decimal

from django.utils import timezone
import pytest

from grading.models import (
    LearnerReportSnapshot,
    ReportSubjectLineSnapshot,
)
from grading.services import compile_assessment, create_report_snapshot_run
from grading.services import create_correction_request, submit_grade_batch


pytestmark = [pytest.mark.django_db, pytest.mark.grading]


def _confirmation(actor, tenant):
    return {
        "actor_id": actor.id,
        "tenant_id": tenant.id,
        "method": "session_step_up",
        "confirmed_at": timezone.now(),
        "confirmation_reference": "session-step-up:phase7a",
    }


def _submit_and_compile(school, assessment, teacher_user, principal_user, student):
    batch = submit_grade_batch(
        actor=teacher_user,
        tenant=school,
        assessment_id=assessment.id,
        payload={"rows": [{"student_id": str(student.id), "raw_score": "84.00"}]},
        idempotency_key=f"phase7a-submit-{student.id}",
        confirmation=_confirmation(teacher_user, school),
    )
    run = compile_assessment(
        tenant=school,
        assessment_id=assessment.id,
        requested_by=principal_user,
    )
    return batch, run


def test_report_snapshot_freezes_compiled_context_and_schema_version(
    school,
    academic_year,
    term,
    assessment,
    teacher_user,
    teacher_assignment,
    principal_user,
    enrolled_student,
):
    assessment.school_grading_schema_version = "schema-v1"
    assessment.save()
    _batch, run = _submit_and_compile(
        school,
        assessment,
        teacher_user,
        principal_user,
        enrolled_student,
    )

    snapshot_run = create_report_snapshot_run(
        actor=principal_user,
        tenant=school,
        academic_year=academic_year,
        term=term,
    )

    learner_snapshot = LearnerReportSnapshot.objects.get(snapshot_run=snapshot_run)
    subject_line = ReportSubjectLineSnapshot.objects.get(snapshot_run=snapshot_run)
    assert learner_snapshot.average_percentage == Decimal("84.00")
    assert subject_line.compilation_run_id == run.id
    assert subject_line.curriculum_version_id == assessment.curriculum_version_id
    assert subject_line.rubric_foundation_id == assessment.rubric_foundation_id
    assert subject_line.school_grading_schema_version == "schema-v1"

    assessment.school_grading_schema_version = "schema-v2"
    assessment.save()
    subject_line.refresh_from_db()
    assert subject_line.school_grading_schema_version == "schema-v1"


def test_pending_correction_blocks_report_snapshot(
    school,
    academic_year,
    term,
    assessment,
    teacher_user,
    teacher_assignment,
    principal_user,
    enrolled_student,
):
    batch, _run = _submit_and_compile(
        school,
        assessment,
        teacher_user,
        principal_user,
        enrolled_student,
    )
    grade_record = batch.grade_records.get()
    create_correction_request(
        actor=teacher_user,
        tenant=school,
        grade_record_id=grade_record.id,
        payload={
            "reason": "Transcription issue pending moderation.",
            "reason_code": "transcription_error",
            "proposed_raw_score": "86.00",
        },
    )

    snapshot_run = create_report_snapshot_run(
        actor=principal_user,
        tenant=school,
        academic_year=academic_year,
        term=term,
    )

    assert snapshot_run.status == snapshot_run.Status.BLOCKED
    assert snapshot_run.learner_snapshots.count() == 0
