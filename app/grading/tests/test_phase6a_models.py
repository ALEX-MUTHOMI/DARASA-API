from decimal import Decimal
from pathlib import Path

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from academics.models import Enrollment, Student
from grading.algorithms.correction_hash import hash_grade_state
from grading.models import (
    Assessment,
    GradeCorrectionRequest,
    GradeRecord,
    GradeSubmissionBatch,
)
from grading.services import build_grade_record, build_submission_batch


pytestmark = [pytest.mark.django_db, pytest.mark.phase6]


def test_grading_models_use_uuid_primary_keys():
    migration = Path(__file__).resolve().parents[1] / "migrations" / "0001_initial.py"
    assert migration.exists()

    for model in [
        Assessment,
        GradeSubmissionBatch,
        GradeRecord,
        GradeCorrectionRequest,
    ]:
        assert model._meta.pk.__class__.__name__ == "UUIDField"


def test_assessment_score_and_tenant_validation(
    assessment,
    other_school,
    academic_year,
    term,
    grade_level,
    other_cohort,
    learning_area,
):
    assessment.max_score = Decimal("0.00")
    with pytest.raises(ValidationError):
        assessment.save()

    with pytest.raises(ValidationError):
        Assessment.objects.create(
            tenant=other_school,
            academic_year=academic_year,
            term=term,
            grade_level=grade_level,
            cohort=other_cohort,
            learning_area=learning_area,
            title="Cross tenant",
            max_score=Decimal("100.00"),
        )


def test_batch_validates_teacher_assignment_and_idempotency(
    school,
    assessment,
    teacher_assignment,
    teacher_user,
):
    batch = build_submission_batch(
        tenant=school,
        actor=teacher_user,
        assessment=assessment,
        teacher_assignment=teacher_assignment,
        idempotency_key="batch-key-1",
        status=GradeSubmissionBatch.Status.SUBMITTED,
    )

    assert batch.teacher == teacher_user
    assert batch.cohort == assessment.cohort
    assert batch.learning_area == assessment.learning_area

    with pytest.raises((IntegrityError, ValidationError)):
        with transaction.atomic():
            build_submission_batch(
                tenant=school,
                actor=teacher_user,
                assessment=assessment,
                teacher_assignment=teacher_assignment,
                idempotency_key="batch-key-1",
                status=GradeSubmissionBatch.Status.SUBMITTED,
            )

    with pytest.raises(ValidationError):
        GradeSubmissionBatch.objects.create(
            tenant=school,
            assessment=assessment,
            teacher=teacher_user,
            teacher_assignment=teacher_assignment,
            cohort=assessment.cohort,
            learning_area=assessment.learning_area,
            status=GradeSubmissionBatch.Status.SUBMITTED,
        )


def test_grade_record_score_bounds_uniqueness_and_roster_validation(
    school,
    assessment,
    teacher_assignment,
    teacher_user,
    enrolled_student,
):
    batch = build_submission_batch(
        tenant=school,
        actor=teacher_user,
        assessment=assessment,
        teacher_assignment=teacher_assignment,
        idempotency_key="batch-key-2",
    )
    record = build_grade_record(
        tenant=school,
        actor=teacher_user,
        assessment=assessment,
        submission_batch=batch,
        student=enrolled_student,
        raw_score=Decimal("80.00"),
        remarks="<b>plain text, not trusted HTML</b>",
    )

    assert record.version == 1
    assert record.remarks.startswith("<b>")

    with pytest.raises(ValidationError):
        build_grade_record(
            tenant=school,
            actor=teacher_user,
            assessment=assessment,
            submission_batch=batch,
            student=enrolled_student,
            raw_score=Decimal("101.00"),
        )

    with pytest.raises((IntegrityError, ValidationError)):
        with transaction.atomic():
            build_grade_record(
                tenant=school,
                actor=teacher_user,
                assessment=assessment,
                submission_batch=batch,
                student=enrolled_student,
                raw_score=Decimal("70.00"),
            )


def test_cross_tenant_student_cannot_be_graded(
    other_school,
    assessment,
    school,
    teacher_assignment,
    teacher_user,
):
    batch = build_submission_batch(
        tenant=school,
        actor=teacher_user,
        assessment=assessment,
        teacher_assignment=teacher_assignment,
        idempotency_key="batch-key-3",
    )
    other_student = Student.objects.create(
        tenant=other_school,
        admission_number="OTH12345",
        first_name="Other",
        last_name="Learner",
    )

    with pytest.raises(ValidationError):
        build_grade_record(
            tenant=school,
            actor=teacher_user,
            assessment=assessment,
            submission_batch=batch,
            student=other_student,
            raw_score=Decimal("60.00"),
        )


def test_unenrolled_student_cannot_be_graded(
    school,
    assessment,
    teacher_assignment,
    teacher_user,
):
    batch = build_submission_batch(
        tenant=school,
        actor=teacher_user,
        assessment=assessment,
        teacher_assignment=teacher_assignment,
        idempotency_key="batch-key-4",
    )
    student = Student.objects.create(
        tenant=school,
        admission_number="UNE12345",
        first_name="No",
        last_name="Enrollment",
    )
    Enrollment.objects.filter(student=student).delete()

    with pytest.raises(ValidationError):
        build_grade_record(
            tenant=school,
            actor=teacher_user,
            assessment=assessment,
            submission_batch=batch,
            student=student,
            raw_score=Decimal("60.00"),
        )


def test_correction_request_requires_reason_hash_and_reviewer_separation(
    school,
    assessment,
    teacher_assignment,
    teacher_user,
    principal_user,
    enrolled_student,
):
    batch = build_submission_batch(
        tenant=school,
        actor=teacher_user,
        assessment=assessment,
        teacher_assignment=teacher_assignment,
        idempotency_key="batch-key-5",
    )
    record = build_grade_record(
        tenant=school,
        actor=teacher_user,
        assessment=assessment,
        submission_batch=batch,
        student=enrolled_student,
        raw_score=Decimal("80.00"),
    )

    old_hash = hash_grade_state(
        {"grade_record_id": str(record.id), "raw_score": str(record.raw_score)}
    )
    correction = GradeCorrectionRequest.objects.create(
        tenant=school,
        grade_record=record,
        requested_by=teacher_user,
        reviewed_by=principal_user,
        reason="Score entry correction requested.",
        old_state_hash=old_hash,
        proposed_raw_score=Decimal("81.00"),
    )

    assert correction.status == GradeCorrectionRequest.Status.REQUESTED

    with pytest.raises(ValidationError):
        GradeCorrectionRequest.objects.create(
            tenant=school,
            grade_record=record,
            requested_by=teacher_user,
            reason="",
            old_state_hash=old_hash,
        )

    with pytest.raises(ValidationError):
        GradeCorrectionRequest.objects.create(
            tenant=school,
            grade_record=record,
            requested_by=teacher_user,
            reason="Missing hash.",
            old_state_hash="",
        )

    with pytest.raises(ValidationError):
        GradeCorrectionRequest.objects.create(
            tenant=school,
            grade_record=record,
            requested_by=teacher_user,
            reviewed_by=teacher_user,
            reason="Self review attempt.",
            old_state_hash=old_hash,
        )
