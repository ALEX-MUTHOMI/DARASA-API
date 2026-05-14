from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from grading.models import GradeSubmissionBatch
from grading.services import build_grade_record, build_submission_batch


pytestmark = [pytest.mark.django_db, pytest.mark.phase6]


def test_submitted_by_and_tenant_are_server_derived(
    school,
    other_school,
    assessment,
    teacher_assignment,
    teacher_user,
    principal_user,
    enrolled_student,
):
    with pytest.raises(ValidationError):
        build_submission_batch(
            tenant=school,
            actor=principal_user,
            assessment=assessment,
            teacher_assignment=teacher_assignment,
            idempotency_key="wrong-actor",
        )

    batch = build_submission_batch(
        tenant=school,
        actor=teacher_user,
        assessment=assessment,
        teacher_assignment=teacher_assignment,
        idempotency_key="shared-computer-batch",
    )
    record = build_grade_record(
        tenant=school,
        actor=teacher_user,
        assessment=assessment,
        submission_batch=batch,
        student=enrolled_student,
        raw_score=Decimal("88.00"),
    )

    assert record.submitted_by == teacher_user
    assert record.tenant == school

    record.tenant = other_school
    with pytest.raises(ValidationError):
        record.save()


def test_status_cannot_be_mass_assigned_to_compiled_without_context(
    school,
    assessment,
    teacher_assignment,
    teacher_user,
):
    with pytest.raises(ValidationError):
        GradeSubmissionBatch.objects.create(
            tenant=school,
            assessment=assessment,
            teacher=teacher_user,
            teacher_assignment=teacher_assignment,
            cohort=assessment.cohort,
            learning_area=assessment.learning_area,
            status=GradeSubmissionBatch.Status.COMPILED,
        )


def test_batch_from_one_school_cannot_attach_to_other_school_assessment(
    other_school,
    assessment,
    teacher_assignment,
    teacher_user,
):
    with pytest.raises(ValidationError):
        GradeSubmissionBatch.objects.create(
            tenant=other_school,
            assessment=assessment,
            teacher=teacher_user,
            teacher_assignment=teacher_assignment,
            cohort=assessment.cohort,
            learning_area=assessment.learning_area,
            idempotency_key="cross-tenant-batch",
            status=GradeSubmissionBatch.Status.SUBMITTED,
        )
