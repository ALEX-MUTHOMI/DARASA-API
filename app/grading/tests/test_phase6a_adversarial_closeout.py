from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from django.core.exceptions import ValidationError

from academics.models import Cohort, LearningArea
from core.policies import PolicyContext
from grading.models import Assessment, GradeCorrectionRequest
from grading.policies import (
    can_enter_grades,
    can_request_grade_correction,
    can_review_grade_correction,
    can_view_grade_records,
)
from grading.services import build_grade_record, build_submission_batch


pytestmark = [pytest.mark.django_db, pytest.mark.phase6]


def _teacher_context(school, teacher_user, role, action):
    return PolicyContext(
        tenant=school,
        actor=teacher_user,
        role=role,
        action=action,
    )


@pytest.mark.parametrize(
    "status",
    [
        Assessment.Status.LOCKED,
        Assessment.Status.SUBMITTED,
        Assessment.Status.APPROVED,
        Assessment.Status.ARCHIVED,
    ],
)
def test_all_operational_statuses_reject_unbound_assessment(
    school,
    academic_year,
    term,
    grade_level,
    cohort,
    learning_area,
    principal_user,
    status,
):
    assessment = Assessment(
        tenant=school,
        academic_year=academic_year,
        term=term,
        grade_level=grade_level,
        cohort=cohort,
        learning_area=learning_area,
        title=f"Unbound {status}",
        max_score=Decimal("100.00"),
        status=status,
        created_by=principal_user,
    )

    with pytest.raises(ValidationError):
        assessment.full_clean()


def test_unknown_assessment_status_fails_closed(
    school,
    academic_year,
    term,
    grade_level,
    cohort,
    learning_area,
    principal_user,
):
    assessment = Assessment(
        tenant=school,
        academic_year=academic_year,
        term=term,
        grade_level=grade_level,
        cohort=cohort,
        learning_area=learning_area,
        title="Unknown status",
        max_score=Decimal("100.00"),
        status="publish_now",
        created_by=principal_user,
    )

    with pytest.raises(ValidationError):
        assessment.full_clean()


def test_teacher_cannot_grade_unassigned_cohort(
    school,
    academic_year,
    term,
    grade_level,
    learning_area,
    curriculum_version,
    curriculum_publication,
    curriculum_rubric_foundation,
    teacher_user,
    subject_teacher_role,
    principal_user,
):
    other_cohort = Cohort.objects.create(
        tenant=school,
        academic_year=academic_year,
        grade_level=grade_level,
        name="Unassigned Closeout Cohort",
    )
    assessment = Assessment.objects.create(
        tenant=school,
        academic_year=academic_year,
        term=term,
        grade_level=grade_level,
        cohort=other_cohort,
        learning_area=learning_area,
        curriculum_version=curriculum_version,
        rubric_foundation=curriculum_rubric_foundation,
        title="Unassigned cohort assessment",
        max_score=Decimal("100.00"),
        status=Assessment.Status.OPEN,
        created_by=principal_user,
    )

    assert not can_enter_grades(
        _teacher_context(
            school,
            teacher_user,
            subject_teacher_role,
            "grading.grades.enter",
        ),
        assessment=assessment,
    )


def test_curriculum_binding_lock_cannot_be_reset_with_normal_save(assessment):
    original_locked_at = assessment.curriculum_binding_locked_at

    assessment.curriculum_binding_locked_at = None
    assessment.save()
    assessment.refresh_from_db()

    assert assessment.curriculum_binding_locked_at is not None
    assert assessment.curriculum_binding_locked_at >= original_locked_at


def test_learning_area_change_after_grading_begins_is_rejected(
    school,
    assessment,
    teacher_user,
    teacher_assignment,
    enrolled_student,
):
    batch = build_submission_batch(
        tenant=school,
        actor=teacher_user,
        assessment=assessment,
        teacher_assignment=teacher_assignment,
        idempotency_key="learning-area-mutation-batch",
    )
    build_grade_record(
        tenant=school,
        actor=teacher_user,
        assessment=assessment,
        submission_batch=batch,
        student=enrolled_student,
        raw_score=Decimal("77.00"),
    )
    other_area = LearningArea.objects.create(
        tenant=school,
        grade_level=assessment.grade_level,
        code="closeout-math",
        name="Mathematics",
    )

    assessment.learning_area = other_area
    with pytest.raises(ValidationError):
        assessment.full_clean()


def test_cross_tenant_correction_access_is_denied(
    school,
    other_school,
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
        idempotency_key="cross-tenant-correction-batch",
    )
    record = build_grade_record(
        tenant=school,
        actor=teacher_user,
        assessment=assessment,
        submission_batch=batch,
        student=enrolled_student,
        raw_score=Decimal("72.00"),
    )
    correction = GradeCorrectionRequest.objects.create(
        tenant=school,
        grade_record=record,
        requested_by=teacher_user,
        reason="Closeout correction request.",
        old_state_hash="sha256:" + "b" * 64,
    )

    assert not can_view_grade_records(
        _teacher_context(
            other_school,
            teacher_user,
            subject_teacher_role,
            "grading.records.view",
        ),
        grade_record=record,
    )
    assert not can_request_grade_correction(
        _teacher_context(
            other_school,
            teacher_user,
            subject_teacher_role,
            "grading.correction.request",
        ),
        grade_record=record,
    )
    assert not can_review_grade_correction(
        PolicyContext(
            tenant=other_school,
            actor=principal_user,
            role=principal_role,
            action="grading.correction.review",
        ),
        correction=correction,
    )


def test_grading_algorithms_are_side_effect_safe():
    algorithm_dir = Path(__file__).resolve().parents[1] / "algorithms"
    forbidden = [
        ".objects.",
        ".save(",
        ".delete(",
        "requests",
        "httpx",
        "urllib",
        "source_url_validator",
        "ssrf_guard",
        "change_detector",
        "regulatory_notice_classifier",
    ]

    for path in algorithm_dir.glob("*.py"):
        source = path.read_text()
        assert all(term not in source for term in forbidden)
