from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from core.models import CustomUser, TenantUserRole
from events.models import EventOutbox, EventTypeRegistry
from events.services import write_outbox_event
from grading.models import GradeRecord
from grading.services import submit_grade_batch


pytestmark = [pytest.mark.django_db, pytest.mark.phase6]


def _confirmation(actor, tenant, **overrides):
    data = {
        "actor_id": actor.id,
        "tenant_id": tenant.id,
        "method": "session_step_up",
        "confirmed_at": timezone.now(),
        "confirmation_reference": "session-step-up:event-test",
    }
    data.update(overrides)
    return data


def _row(student, score="80.00"):
    return {"student_id": str(student.id), "raw_score": score, "remarks": "ok"}


def _second_teacher(school, role, assignment):
    user = CustomUser.objects.create_user(
        email=f"p6b-second-{school.id}@example.test",
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


def test_grading_batch_contract_is_versioned_fact_and_allowlisted():
    contract = EventTypeRegistry.objects.get(
        event_type="grading.batch_submitted",
        event_version=1,
    )

    assert contract.is_active is True
    assert contract.allowed_producers == ["grading"]
    assert contract.requires_tenant is True
    assert "batch_id" in contract.payload_schema["required"]
    assert "curriculum_version_id" in contract.payload_schema["required"]

    command_contract = EventTypeRegistry(
        event_type="grading.send_message_now",
        event_version=1,
        description="Invalid command-shaped event.",
        source_module="grading",
        allowed_producers=["grading"],
        allowed_consumers=["audit"],
        requires_tenant=True,
        payload_schema={"required": ["batch_id"]},
    )
    with pytest.raises(ValidationError):
        command_contract.full_clean()


def test_unapproved_producer_cannot_emit_grading_event(school, assessment):
    with pytest.raises(ValidationError):
        write_outbox_event(
            event_type="grading.batch_submitted",
            event_version=1,
            source_module="academics",
            idempotency_key="wrong-producer",
            tenant=school,
            payload={
                "tenant_id": str(school.id),
                "assessment_id": str(assessment.id),
                "batch_id": "batch-id",
                "cohort_id": str(assessment.cohort_id),
                "learning_area_id": str(assessment.learning_area_id),
                "curriculum_version_id": str(assessment.curriculum_version_id),
                "record_count": 1,
                "submitted_at": timezone.now().isoformat(),
            },
        )


def test_failed_submission_paths_emit_no_event(
    school,
    assessment,
    teacher_user,
    teacher_assignment,
    enrolled_student,
):
    payload = {"rows": [_row(enrolled_student)]}

    bad_payloads = [
        (payload, {}),
        (
            {"rows": [{"student_id": "00000000-0000-0000-0000-000000000000"}]},
            _confirmation(teacher_user, school),
        ),
        (
            {"rows": [_row(enrolled_student, "101.00")]},
            _confirmation(teacher_user, school),
        ),
        (
            {"rows": [_row(enrolled_student), _row(enrolled_student)]},
            _confirmation(teacher_user, school),
        ),
    ]
    for index, (bad_payload, confirmation) in enumerate(bad_payloads, start=1):
        with pytest.raises(ValidationError):
            submit_grade_batch(
                actor=teacher_user,
                tenant=school,
                assessment_id=assessment.id,
                payload=bad_payload,
                idempotency_key=f"failed-submit-{index}",
                confirmation=confirmation,
            )

    assert EventOutbox.objects.filter(event_type="grading.batch_submitted").count() == 0
    assert GradeRecord.objects.count() == 0


def test_rollback_discards_grade_records_and_batch_event(
    school,
    assessment,
    teacher_user,
    teacher_assignment,
    enrolled_student,
):
    with pytest.raises(RuntimeError):
        with transaction.atomic():
            submit_grade_batch(
                actor=teacher_user,
                tenant=school,
                assessment_id=assessment.id,
                payload={"rows": [_row(enrolled_student, "82.00")]},
                idempotency_key="rollback-submit",
                confirmation=_confirmation(teacher_user, school),
            )
            raise RuntimeError("force rollback")

    assert GradeRecord.objects.count() == 0
    assert EventOutbox.objects.filter(event_type="grading.batch_submitted").count() == 0


def test_successful_submit_and_retry_emit_exactly_one_compact_event(
    school,
    assessment,
    teacher_user,
    teacher_assignment,
    enrolled_student,
    django_capture_on_commit_callbacks,
):
    payload = {"rows": [_row(enrolled_student, "83.00")]}

    with django_capture_on_commit_callbacks(execute=True):
        batch = submit_grade_batch(
            actor=teacher_user,
            tenant=school,
            assessment_id=assessment.id,
            payload=payload,
            idempotency_key="submit-once",
            confirmation=_confirmation(teacher_user, school),
        )
    retry = submit_grade_batch(
        actor=teacher_user,
        tenant=school,
        assessment_id=assessment.id,
        payload=payload,
        idempotency_key="submit-once",
        confirmation=_confirmation(teacher_user, school),
    )

    event = EventOutbox.objects.get(event_type="grading.batch_submitted")
    assert retry.id == batch.id
    assert event.event_version == 1
    assert event.payload["batch_id"] == str(batch.id)
    assert event.payload["record_count"] == 1
    assert "raw_marks" not in event.payload
    assert "component_scores" not in event.payload
    assert "learner_names" not in event.payload
    assert EventOutbox.objects.filter(event_type="grading.batch_submitted").count() == 1
    assert GradeRecord.objects.filter(assessment=assessment).count() == 1


def test_submission_idempotency_key_cannot_cross_teacher_context(
    school,
    assessment,
    teacher_user,
    teacher_assignment,
    subject_teacher_role,
    enrolled_student,
    django_capture_on_commit_callbacks,
):
    payload = {"rows": [_row(enrolled_student, "74.00")]}
    with django_capture_on_commit_callbacks(execute=True):
        submit_grade_batch(
            actor=teacher_user,
            tenant=school,
            assessment_id=assessment.id,
            payload=payload,
            idempotency_key="shared-submit-key",
            confirmation=_confirmation(teacher_user, school),
        )
    other_teacher = _second_teacher(school, subject_teacher_role, teacher_assignment)

    with pytest.raises(ValidationError):
        submit_grade_batch(
            actor=other_teacher,
            tenant=school,
            assessment_id=assessment.id,
            payload=payload,
            idempotency_key="shared-submit-key",
            confirmation=_confirmation(other_teacher, school),
        )


def test_payload_schema_rejects_raw_marks_and_learner_names(school, assessment):
    base_payload = {
        "tenant_id": str(school.id),
        "assessment_id": str(assessment.id),
        "batch_id": "batch-id",
        "cohort_id": str(assessment.cohort_id),
        "learning_area_id": str(assessment.learning_area_id),
        "curriculum_version_id": str(assessment.curriculum_version_id),
        "record_count": 1,
        "submitted_at": timezone.now().isoformat(),
    }

    for forbidden_key, forbidden_value in [
        ("raw_marks", ["50.00"]),
        ("component_scores", {"component-1": "10.00"}),
        ("learner_names", ["Test Learner"]),
        ("raw_grade_grid", {"rows": []}),
    ]:
        payload = {**base_payload, forbidden_key: forbidden_value}
        with pytest.raises(ValidationError):
            write_outbox_event(
                event_type="grading.batch_submitted",
                event_version=1,
                source_module="grading",
                idempotency_key=f"bad-event-{forbidden_key}",
                tenant=school,
                payload=payload,
            )
