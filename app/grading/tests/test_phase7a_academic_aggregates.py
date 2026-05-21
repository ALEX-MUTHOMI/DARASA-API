from __future__ import annotations

from django.utils import timezone
import pytest

from grading.models import AcademicAggregate
from grading.services import (
    compile_assessment,
    create_report_snapshot_run,
    submit_grade_batch,
)


pytestmark = [pytest.mark.django_db, pytest.mark.grading]


def _confirmation(actor, tenant):
    return {
        "actor_id": actor.id,
        "tenant_id": tenant.id,
        "method": "session_step_up",
        "confirmed_at": timezone.now(),
        "confirmation_reference": "session-step-up:phase7a-aggregate",
    }


def test_academic_aggregates_are_tenant_and_report_period_scoped(
    school,
    other_school,
    academic_year,
    term,
    assessment,
    teacher_user,
    teacher_assignment,
    principal_user,
    enrolled_student,
):
    submit_grade_batch(
        actor=teacher_user,
        tenant=school,
        assessment_id=assessment.id,
        payload={
            "rows": [
                {"student_id": str(enrolled_student.id), "raw_score": "78.00"}
            ]
        },
        idempotency_key="phase7a-aggregate-submit",
        confirmation=_confirmation(teacher_user, school),
    )
    compile_assessment(
        tenant=school,
        assessment_id=assessment.id,
        requested_by=principal_user,
    )

    snapshot_run = create_report_snapshot_run(
        actor=principal_user,
        tenant=school,
        academic_year=academic_year,
        term=term,
    )

    assert (
        AcademicAggregate.objects.filter(
            tenant=school,
            snapshot_run=snapshot_run,
        ).count()
        >= 4
    )
    assert AcademicAggregate.objects.filter(tenant=other_school).count() == 0
    school_aggregate = AcademicAggregate.objects.get(
        tenant=school,
        snapshot_run=snapshot_run,
        scope_type=AcademicAggregate.ScopeType.SCHOOL,
    )
    assert school_aggregate.metrics["mean_percentage"] == "78.00"
    assert school_aggregate.metrics["learner_count"] == 1
    assert school_aggregate.min_group_size_met is False
