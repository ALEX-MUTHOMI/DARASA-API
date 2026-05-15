from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from academics.models import Enrollment, Student
from events.models import EventOutbox
from grading.models import AssessmentComponent, GradeRecord
from grading.services import (
    build_grade_grid,
    get_my_grading_work,
    save_grade_draft,
    submit_grade_batch,
)


pytestmark = [pytest.mark.django_db, pytest.mark.phase6]


def _confirmation(actor, tenant, **overrides):
    data = {
        "actor_id": actor.id,
        "tenant_id": tenant.id,
        "method": "session_step_up",
        "confirmed_at": timezone.now(),
        "confirmation_reference": "session-step-up:fixture",
    }
    data.update(overrides)
    return data


def _row(student, score="80.00", **extra):
    data = {"student_id": str(student.id), "raw_score": score, "remarks": "ok"}
    data.update(extra)
    return data


def test_teacher_workload_lists_only_assigned_open_bound_contexts(
    school,
    assessment,
    teacher_user,
    teacher_assignment,
):
    work = get_my_grading_work(actor=teacher_user, tenant=school)

    assert [item["assessment_id"] for item in work] == [str(assessment.id)]
    assert work[0]["curriculum_version_id"] == str(assessment.curriculum_version_id)


def test_grid_includes_bound_assessment_roster_and_draft_values(
    school,
    assessment,
    teacher_user,
    teacher_assignment,
    enrolled_student,
):
    draft = save_grade_draft(
        actor=teacher_user,
        tenant=school,
        assessment_id=assessment.id,
        payload={"rows": [_row(enrolled_student, "67.00")]},
        idempotency_key="grid-draft-1",
    )

    grid = build_grade_grid(
        actor=teacher_user,
        tenant=school,
        assessment_id=assessment.id,
    )

    assert grid["assessment"]["assessment_id"] == str(assessment.id)
    assert grid["assessment"]["curriculum_version_id"] == str(
        assessment.curriculum_version_id
    )
    assert grid["draft"]["draft_id"] == str(draft.id)
    assert grid["rows"][0]["student_id"] == str(enrolled_student.id)
    assert grid["rows"][0]["draft"]["raw_score"] == "67.00"


def test_draft_save_resume_idempotency_and_conflict_protection(
    school,
    assessment,
    teacher_user,
    teacher_assignment,
    enrolled_student,
):
    payload = {"rows": [_row(enrolled_student, "70.00")]}
    draft = save_grade_draft(
        actor=teacher_user,
        tenant=school,
        assessment_id=assessment.id,
        payload=payload,
        idempotency_key="draft-idempotent",
    )
    retry = save_grade_draft(
        actor=teacher_user,
        tenant=school,
        assessment_id=assessment.id,
        payload=payload,
        idempotency_key="draft-idempotent",
    )
    assert retry.id == draft.id
    assert GradeRecord.objects.count() == 0

    with pytest.raises(ValidationError):
        save_grade_draft(
            actor=teacher_user,
            tenant=school,
            assessment_id=assessment.id,
            payload={
                "draft_version": draft.version + 1,
                "rows": [_row(enrolled_student, "71.00")],
            },
            idempotency_key="draft-stale",
        )

    with pytest.raises(ValidationError):
        save_grade_draft(
            actor=teacher_user,
            tenant=school,
            assessment_id=assessment.id,
            payload={
                "draft_version": draft.version,
                "rows": [_row(enrolled_student), _row(enrolled_student)],
            },
            idempotency_key="draft-duplicate-row",
        )


def test_final_submission_requires_step_up_and_emits_one_compact_event(
    school,
    assessment,
    teacher_user,
    teacher_assignment,
    enrolled_student,
    django_capture_on_commit_callbacks,
):
    payload = {"rows": [_row(enrolled_student, "81.00")]}

    with pytest.raises(ValidationError):
        submit_grade_batch(
            actor=teacher_user,
            tenant=school,
            assessment_id=assessment.id,
            payload=payload,
            idempotency_key="submit-missing-confirmation",
            confirmation={},
        )

    with django_capture_on_commit_callbacks(execute=True):
        batch = submit_grade_batch(
            actor=teacher_user,
            tenant=school,
            assessment_id=assessment.id,
            payload=payload,
            idempotency_key="submit-final-1",
            confirmation=_confirmation(teacher_user, school),
        )

    assert batch.record_count == 1
    assert batch.teacher == teacher_user
    assert GradeRecord.objects.get(submission_batch=batch).raw_score == Decimal("81.00")

    event = EventOutbox.objects.get(event_type="grading.batch_submitted")
    assert event.tenant == school
    assert event.payload["batch_id"] == str(batch.id)
    assert event.payload["curriculum_version_id"] == str(
        assessment.curriculum_version_id
    )
    assert "raw_marks" not in event.payload
    assert "learner_names" not in event.payload

    retry = submit_grade_batch(
        actor=teacher_user,
        tenant=school,
        assessment_id=assessment.id,
        payload=payload,
        idempotency_key="submit-final-1",
        confirmation=_confirmation(teacher_user, school),
    )
    assert retry.id == batch.id
    assert GradeRecord.objects.filter(assessment=assessment).count() == 1


def test_same_submission_key_with_different_payload_is_rejected(
    school,
    assessment,
    teacher_user,
    teacher_assignment,
    enrolled_student,
    django_capture_on_commit_callbacks,
):
    with django_capture_on_commit_callbacks(execute=True):
        submit_grade_batch(
            actor=teacher_user,
            tenant=school,
            assessment_id=assessment.id,
            payload={"rows": [_row(enrolled_student, "75.00")]},
            idempotency_key="submit-conflict",
            confirmation=_confirmation(teacher_user, school),
        )

    with pytest.raises(ValidationError):
        submit_grade_batch(
            actor=teacher_user,
            tenant=school,
            assessment_id=assessment.id,
            payload={"rows": [_row(enrolled_student, "76.00")]},
            idempotency_key="submit-conflict",
            confirmation=_confirmation(teacher_user, school),
        )


def test_confirmation_actor_tenant_and_expiry_are_enforced(
    school,
    other_school,
    assessment,
    teacher_user,
    teacher_assignment,
    enrolled_student,
):
    payload = {"rows": [_row(enrolled_student, "70.00")]}

    for confirmation in [
        _confirmation(teacher_user, school, actor_id="wrong"),
        _confirmation(teacher_user, other_school),
        _confirmation(
            teacher_user,
            school,
            confirmed_at=timezone.now() - timedelta(minutes=10),
        ),
        _confirmation(teacher_user, school, password="raw-secret"),
    ]:
        with pytest.raises(ValidationError):
            submit_grade_batch(
                actor=teacher_user,
                tenant=school,
                assessment_id=assessment.id,
                payload=payload,
                idempotency_key=f"bad-confirm-{confirmation.get('tenant_id')}",
                confirmation=confirmation,
            )


def test_practical_component_grid_and_validation(
    school,
    assessment,
    teacher_user,
    teacher_assignment,
    enrolled_student,
):
    component = AssessmentComponent.objects.create(
        tenant=school,
        assessment=assessment,
        name="Practical setup",
        max_score=Decimal("40.00"),
        order=1,
        is_required=True,
        rubric_foundation=assessment.rubric_foundation,
    )
    grid = build_grade_grid(
        actor=teacher_user,
        tenant=school,
        assessment_id=assessment.id,
    )
    assert grid["assessment"]["mode"] == "component"
    assert grid["columns"][0]["component_id"] == str(component.id)

    with pytest.raises(ValidationError):
        submit_grade_batch(
            actor=teacher_user,
            tenant=school,
            assessment_id=assessment.id,
            payload={"rows": [{"student_id": str(enrolled_student.id)}]},
            idempotency_key="missing-component",
            confirmation=_confirmation(teacher_user, school),
        )
    with pytest.raises(ValidationError):
        submit_grade_batch(
            actor=teacher_user,
            tenant=school,
            assessment_id=assessment.id,
            payload={
                "rows": [
                    {
                        "student_id": str(enrolled_student.id),
                        "component_scores": {str(component.id): "41.00"},
                    }
                ]
            },
            idempotency_key="component-above-max",
            confirmation=_confirmation(teacher_user, school),
        )


def test_payload_mass_assignment_and_invalid_roster_are_rejected(
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
                "status": "submitted",
                "rows": [_row(enrolled_student)],
            },
            idempotency_key="draft-mass-assignment",
        )

    with pytest.raises(ValidationError):
        submit_grade_batch(
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
            idempotency_key="invalid-roster-submit",
            confirmation=_confirmation(teacher_user, school),
        )


def test_grid_roster_excludes_inactive_learners(
    school,
    assessment,
    teacher_user,
    teacher_assignment,
    cohort,
    academic_year,
    term,
):
    inactive = Student.objects.create(
        tenant=school,
        admission_number="INACTIVE-P6B",
        first_name="Inactive",
        last_name="Learner",
        is_active=False,
    )
    Enrollment.objects.create(
        tenant=school,
        student=inactive,
        cohort=cohort,
        academic_year=academic_year,
        term=term,
    )

    grid = build_grade_grid(
        actor=teacher_user,
        tenant=school,
        assessment_id=assessment.id,
    )

    assert str(inactive.id) not in [row["student_id"] for row in grid["rows"]]
