from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from academics.models import LearningArea, TeacherAssignment
from core.models import TenantUserRole
from core.policies import PolicyContext
from grading.models import Assessment
from grading.policies import (
    can_enter_grades,
    can_review_grade_correction,
    can_submit_grade_batch,
    can_view_assessment,
    can_view_grade_records,
)
from grading.services import build_grade_record, build_submission_batch


pytestmark = [pytest.mark.django_db, pytest.mark.phase6]


def _context(school, teacher_user, subject_teacher_role, action):
    return PolicyContext(
        tenant=school,
        actor=teacher_user,
        role=subject_teacher_role,
        action=action,
    )


def test_teacher_can_grade_only_assigned_context(
    school,
    assessment,
    teacher_user,
    teacher_assignment,
    subject_teacher_role,
):
    context = _context(
        school,
        teacher_user,
        subject_teacher_role,
        "grading.grades.enter",
    )

    assert can_view_assessment(
        _context(school, teacher_user, subject_teacher_role, "grading.assessment.view"),
        assessment=assessment,
    )
    assert can_enter_grades(context, assessment=assessment)
    assert can_submit_grade_batch(
        _context(school, teacher_user, subject_teacher_role, "grading.batch.submit"),
        assessment=assessment,
    )

    teacher_assignment.is_active = False
    teacher_assignment.save(update_fields=["is_active"])
    assert not can_enter_grades(context, assessment=assessment)


def test_teacher_assigned_to_other_learning_area_cannot_grade(
    school,
    academic_year,
    term,
    grade_level,
    cohort,
    teacher_user,
    subject_teacher_role,
    principal_user,
):
    other_area = LearningArea.objects.create(
        tenant=school,
        grade_level=grade_level,
        code="math-area",
        name="Mathematics",
    )
    TeacherAssignment.objects.create(
        tenant=school,
        teacher=teacher_user,
        cohort=cohort,
        learning_area=other_area,
        academic_year=academic_year,
        term=term,
    )
    assessment = Assessment.objects.create(
        tenant=school,
        academic_year=academic_year,
        term=term,
        grade_level=grade_level,
        cohort=cohort,
        learning_area=LearningArea.objects.create(
            tenant=school,
            grade_level=grade_level,
            code="computer-extra",
            name="Computer Studies",
        ),
        title="Unassigned",
        max_score=Decimal("100.00"),
        status=Assessment.Status.OPEN,
        created_by=principal_user,
    )

    assert not can_enter_grades(
        _context(school, teacher_user, subject_teacher_role, "grading.grades.enter"),
        assessment=assessment,
    )


def test_inactive_role_binding_denies_access(
    school,
    assessment,
    teacher_user,
    teacher_assignment,
    subject_teacher_role,
):
    TenantUserRole.objects.filter(
        tenant=school,
        user=teacher_user,
        role=subject_teacher_role,
    ).update(is_active=False)

    assert not can_enter_grades(
        _context(school, teacher_user, subject_teacher_role, "grading.grades.enter"),
        assessment=assessment,
    )


def test_grade_record_and_correction_policy_fail_closed(
    school,
    assessment,
    teacher_assignment,
    teacher_user,
    principal_user,
    subject_teacher_role,
    principal_role,
    enrolled_student,
):
    batch = build_submission_batch(
        tenant=school,
        actor=teacher_user,
        assessment=assessment,
        teacher_assignment=teacher_assignment,
        idempotency_key="policy-batch",
    )
    record = build_grade_record(
        tenant=school,
        actor=teacher_user,
        assessment=assessment,
        submission_batch=batch,
        student=enrolled_student,
        raw_score=Decimal("75.00"),
    )

    assert can_view_grade_records(
        _context(school, teacher_user, subject_teacher_role, "grading.records.view"),
        grade_record=record,
    )
    with pytest.raises(ValidationError):
        record.raw_score = Decimal("101.00")
        record.save()

    from grading.models import GradeCorrectionRequest

    correction = GradeCorrectionRequest.objects.create(
        tenant=school,
        grade_record=record,
        requested_by=teacher_user,
        reason="Review needed.",
        old_state_hash="sha256:" + "a" * 64,
    )

    assert not can_review_grade_correction(
        _context(
            school,
            teacher_user,
            subject_teacher_role,
            "grading.correction.review",
        ),
        correction=correction,
    )
    assert can_review_grade_correction(
        PolicyContext(
            tenant=school,
            actor=principal_user,
            role=principal_role,
            action="grading.correction.review",
        ),
        correction=correction,
    )
