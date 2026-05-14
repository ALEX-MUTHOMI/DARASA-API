from decimal import Decimal

import pytest

from grading.selectors import (
    get_assessment_for_teacher,
    get_grade_records_for_assessment,
    get_submission_batches_for_assessment,
    get_teacher_grading_contexts,
)
from grading.services import build_grade_record, build_submission_batch


pytestmark = [pytest.mark.django_db, pytest.mark.phase6]


def test_teacher_grading_contexts_are_assignment_scoped(
    school,
    teacher_user,
    assessment,
    teacher_assignment,
):
    contexts = list(get_teacher_grading_contexts(actor=teacher_user, tenant=school))

    assert contexts == [assessment]
    assert list(get_teacher_grading_contexts(actor=teacher_user, tenant=None)) == []


def test_assessment_selector_denies_idor_and_cross_tenant_access(
    school,
    other_school,
    assessment,
    teacher_user,
    teacher_assignment,
):
    assert (
        get_assessment_for_teacher(
            actor=teacher_user,
            tenant=school,
            assessment_id=assessment.id,
        )
        == assessment
    )
    assert (
        get_assessment_for_teacher(
            actor=teacher_user,
            tenant=other_school,
            assessment_id=assessment.id,
        )
        is None
    )
    assert (
        get_assessment_for_teacher(
            actor=teacher_user,
            tenant=school,
            assessment_id="not-a-uuid",
        )
        is None
    )


def test_grade_record_and_batch_selectors_are_tenant_and_assignment_scoped(
    school,
    other_school,
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
        idempotency_key="selector-batch",
    )
    record = build_grade_record(
        tenant=school,
        actor=teacher_user,
        assessment=assessment,
        submission_batch=batch,
        student=enrolled_student,
        raw_score=Decimal("70.00"),
    )

    assert list(
        get_grade_records_for_assessment(
            actor=teacher_user,
            tenant=school,
            assessment_id=assessment.id,
        )
    ) == [record]
    assert list(
        get_submission_batches_for_assessment(
            actor=teacher_user,
            tenant=school,
            assessment_id=assessment.id,
        )
    ) == [batch]
    assert list(
        get_grade_records_for_assessment(
            actor=teacher_user,
            tenant=other_school,
            assessment_id=assessment.id,
        )
    ) == []
