from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError

from core.models import CustomUser, TenantUserRole
from events.models import EventOutbox
from grading.models import GradeDraftBatch, GradeRecord
from grading.selectors import get_existing_draft_for_teacher
from grading.services import build_grade_grid, save_grade_draft


pytestmark = [pytest.mark.django_db, pytest.mark.phase6]


def _row(student, score="70.00"):
    return {"student_id": str(student.id), "raw_score": score, "remarks": "draft"}


def _assigned_teacher(school, role, assignment):
    user = CustomUser.objects.create_user(
        email=f"p6b-draft-{school.id}@example.test",
        password="test-only-secret",
    )
    TenantUserRole.objects.create(tenant=school, user=user, role=role)
    assignment.__class__.objects.create(
        tenant=school,
        teacher=user,
        cohort=assignment.cohort,
        learning_area=assignment.learning_area,
        academic_year=assignment.academic_year,
        term=assignment.term,
    )
    return user


def test_draft_is_teacher_tenant_and_assessment_scoped(
    school,
    other_school,
    assessment,
    teacher_user,
    teacher_assignment,
    subject_teacher_role,
    enrolled_student,
):
    draft = save_grade_draft(
        actor=teacher_user,
        tenant=school,
        assessment_id=assessment.id,
        payload={"rows": [_row(enrolled_student, "71.00")]},
        idempotency_key="teacher-owned-draft",
    )
    other_teacher = _assigned_teacher(school, subject_teacher_role, teacher_assignment)

    assert get_existing_draft_for_teacher(
        actor=teacher_user,
        tenant=school,
        assessment=assessment,
    ).id == draft.id
    assert get_existing_draft_for_teacher(
        actor=other_teacher,
        tenant=school,
        assessment=assessment,
    ) is None
    assert get_existing_draft_for_teacher(
        actor=teacher_user,
        tenant=other_school,
        assessment=assessment,
    ) is None


def test_another_assigned_teacher_does_not_receive_owner_draft_values(
    school,
    assessment,
    teacher_user,
    teacher_assignment,
    subject_teacher_role,
    enrolled_student,
):
    save_grade_draft(
        actor=teacher_user,
        tenant=school,
        assessment_id=assessment.id,
        payload={"rows": [_row(enrolled_student, "72.00")]},
        idempotency_key="owner-visible-draft",
    )
    other_teacher = _assigned_teacher(school, subject_teacher_role, teacher_assignment)

    grid = build_grade_grid(
        actor=other_teacher,
        tenant=school,
        assessment_id=assessment.id,
    )

    assert "draft" not in grid
    assert grid["rows"][0]["draft"] is None


def test_draft_idempotency_rejects_different_payload_or_context(
    school,
    assessment,
    teacher_user,
    teacher_assignment,
    subject_teacher_role,
    enrolled_student,
):
    payload = {"rows": [_row(enrolled_student, "73.00")]}
    draft = save_grade_draft(
        actor=teacher_user,
        tenant=school,
        assessment_id=assessment.id,
        payload=payload,
        idempotency_key="draft-key-conflict",
    )

    with pytest.raises(ValidationError):
        save_grade_draft(
            actor=teacher_user,
            tenant=school,
            assessment_id=assessment.id,
            payload={"rows": [_row(enrolled_student, "74.00")]},
            idempotency_key="draft-key-conflict",
        )

    other_teacher = _assigned_teacher(school, subject_teacher_role, teacher_assignment)
    with pytest.raises(ValidationError):
        save_grade_draft(
            actor=other_teacher,
            tenant=school,
            assessment_id=assessment.id,
            payload=payload,
            idempotency_key="draft-key-conflict",
        )

    assert GradeDraftBatch.objects.get(id=draft.id).teacher == teacher_user


def test_invalid_draft_rows_do_not_create_official_records_or_events(
    school,
    assessment,
    teacher_user,
    teacher_assignment,
    enrolled_student,
):
    with pytest.raises(ValidationError):
        save_grade_draft(
            actor=teacher_user,
            tenant=school,
            assessment_id=assessment.id,
            payload={
                "rows": [
                    {
                        "student_id": "00000000-0000-0000-0000-000000000000",
                        "raw_score": "50.00",
                    }
                ]
            },
            idempotency_key="invalid-draft-learner",
        )

    save_grade_draft(
        actor=teacher_user,
        tenant=school,
        assessment_id=assessment.id,
        payload={"rows": [_row(enrolled_student, "75.00")]},
        idempotency_key="draft-no-event",
    )

    assert GradeRecord.objects.count() == 0
    assert EventOutbox.objects.filter(event_type="grading.batch_submitted").count() == 0
