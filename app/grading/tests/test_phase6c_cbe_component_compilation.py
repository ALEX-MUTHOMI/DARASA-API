from __future__ import annotations

from decimal import Decimal

from django.utils import timezone
import pytest

from grading.models import AssessmentComponent, CompiledLearnerSnapshot
from grading.services import compile_assessment, submit_grade_batch


pytestmark = [pytest.mark.django_db, pytest.mark.phase6]


def _confirmation(actor, tenant):
    return {
        "actor_id": actor.id,
        "tenant_id": tenant.id,
        "method": "session_step_up",
        "confirmed_at": timezone.now(),
        "confirmation_reference": "session-step-up:components",
    }


def test_component_assessment_compiles_ordered_component_summary(
    school,
    assessment,
    teacher_user,
    teacher_assignment,
    principal_user,
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
    submit_grade_batch(
        actor=teacher_user,
        tenant=school,
        assessment_id=assessment.id,
        payload={
            "rows": [
                {
                    "student_id": str(enrolled_student.id),
                    "component_scores": {str(component.id): "35.00"},
                }
            ]
        },
        idempotency_key="component-compile-submit",
        confirmation=_confirmation(teacher_user, school),
    )

    run = compile_assessment(
        tenant=school,
        assessment_id=assessment.id,
        requested_by=principal_user,
    )

    snapshot = CompiledLearnerSnapshot.objects.get(compilation_run=run)
    assert snapshot.component_summary["component_total"] == "35.00"
    assert snapshot.component_summary["components"][0]["component_id"] == str(
        component.id
    )
    assert snapshot.cbe_band_status == "unresolved_due_to_missing_rubric_mapping"
