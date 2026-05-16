from __future__ import annotations

from django.db import transaction
from django.utils import timezone
import pytest

from events.models import EventOutbox, EventTypeRegistry
from grading.models import CompilationRun
from grading.services import compile_assessment, submit_grade_batch


pytestmark = [pytest.mark.django_db, pytest.mark.phase6]


def _confirmation(actor, tenant):
    return {
        "actor_id": actor.id,
        "tenant_id": tenant.id,
        "method": "session_step_up",
        "confirmed_at": timezone.now(),
        "confirmation_reference": "session-step-up:compile-event",
    }


def _submit(school, assessment, teacher_user, enrolled_student):
    submit_grade_batch(
        actor=teacher_user,
        tenant=school,
        assessment_id=assessment.id,
        payload={"rows": [{"student_id": str(enrolled_student.id), "raw_score": "80"}]},
        idempotency_key="compile-event-submit",
        confirmation=_confirmation(teacher_user, school),
    )


def test_compilation_event_contract_is_versioned_and_compact():
    contract = EventTypeRegistry.objects.get(
        event_type="grading.compilation_completed",
        event_version=1,
    )

    assert contract.allowed_producers == ["grading"]
    assert contract.requires_tenant is True
    assert "compilation_run_id" in contract.payload_schema["required"]


def test_compilation_event_emits_after_commit_only(
    school,
    assessment,
    teacher_user,
    teacher_assignment,
    principal_user,
    enrolled_student,
    django_capture_on_commit_callbacks,
):
    _submit(school, assessment, teacher_user, enrolled_student)

    with pytest.raises(RuntimeError):
        with transaction.atomic():
            compile_assessment(
                tenant=school,
                assessment_id=assessment.id,
                requested_by=principal_user,
            )
            raise RuntimeError("rollback compilation")

    assert CompilationRun.objects.count() == 0
    assert EventOutbox.objects.filter(
        event_type="grading.compilation_completed",
    ).count() == 0

    with django_capture_on_commit_callbacks(execute=True):
        run = compile_assessment(
            tenant=school,
            assessment_id=assessment.id,
            requested_by=principal_user,
        )

    event = EventOutbox.objects.get(event_type="grading.compilation_completed")
    assert event.payload["compilation_run_id"] == str(run.id)
    assert "raw_marks" not in event.payload
    assert "learner_names" not in event.payload
    assert "full_report_text" not in event.payload
