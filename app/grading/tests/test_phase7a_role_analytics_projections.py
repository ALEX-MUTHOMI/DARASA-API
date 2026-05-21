from __future__ import annotations

from django.utils import timezone
import pytest

from academics.models import TeacherAssignment
from core.models import CustomUser, Role, TenantUserRole
from grading.services import (
    compile_assessment,
    create_report_snapshot_run,
    get_class_teacher_analytics_projection,
    get_future_parent_snapshot_projection,
    get_hod_analytics_projection,
    get_principal_analytics_projection,
    get_subject_teacher_analytics_projection,
    submit_grade_batch,
)


pytestmark = [pytest.mark.django_db, pytest.mark.grading]


def _confirmation(actor, tenant):
    return {
        "actor_id": actor.id,
        "tenant_id": tenant.id,
        "method": "session_step_up",
        "confirmed_at": timezone.now(),
        "confirmation_reference": "session-step-up:phase7a-roles",
    }


def _role_user(school, role_code: str) -> CustomUser:
    role, _ = Role.objects.get_or_create(
        code=role_code,
        defaults={"name": role_code.replace("_", " ").title()},
    )
    user = CustomUser.objects.create_user(
        email=f"phase7a-{role_code}-{school.id}@example.test",
        password="test-only-secret",
    )
    TenantUserRole.objects.create(tenant=school, user=user, role=role)
    return user


def _build_snapshot(
    school,
    academic_year,
    term,
    assessment,
    teacher_user,
    principal_user,
    enrolled_student,
):
    submit_grade_batch(
        actor=teacher_user,
        tenant=school,
        assessment_id=assessment.id,
        payload={
            "rows": [
                {"student_id": str(enrolled_student.id), "raw_score": "88.00"}
            ]
        },
        idempotency_key="phase7a-role-submit",
        confirmation=_confirmation(teacher_user, school),
    )
    compile_assessment(
        tenant=school,
        assessment_id=assessment.id,
        requested_by=principal_user,
    )
    return create_report_snapshot_run(
        actor=principal_user,
        tenant=school,
        academic_year=academic_year,
        term=term,
    )


def test_role_analytics_are_scoped_and_parent_fails_closed(
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
    _build_snapshot(
        school,
        academic_year,
        term,
        assessment,
        teacher_user,
        principal_user,
        enrolled_student,
    )
    hod = _role_user(school, Role.RoleCode.HOD.value)
    TeacherAssignment.objects.create(
        tenant=school,
        teacher=hod,
        cohort=assessment.cohort,
        learning_area=assessment.learning_area,
        academic_year=academic_year,
        term=term,
    )
    class_teacher = _role_user(school, Role.RoleCode.CLASS_TEACHER.value)
    TeacherAssignment.objects.create(
        tenant=school,
        teacher=class_teacher,
        cohort=assessment.cohort,
        learning_area=assessment.learning_area,
        academic_year=academic_year,
        term=term,
    )

    principal_projection = get_principal_analytics_projection(
        actor=principal_user,
        tenant=school,
    )
    assert principal_projection["projection_type"] == "principal"
    assert principal_projection["snapshot_count"] == 1
    assert "raw_grade_grid" not in principal_projection

    cross_tenant_projection = get_principal_analytics_projection(
        actor=principal_user,
        tenant=other_school,
    )
    assert cross_tenant_projection["snapshot_count"] == 0

    hod_projection = get_hod_analytics_projection(actor=hod, tenant=school)
    assert hod_projection["snapshot_count"] == 1
    assert all(
        item["learning_area_id"] in {"", str(assessment.learning_area_id)}
        for item in hod_projection["aggregates"]
    )

    class_projection = get_class_teacher_analytics_projection(
        actor=class_teacher,
        tenant=school,
        cohort_id=assessment.cohort_id,
    )
    assert class_projection["projection_type"] == "class_teacher"
    assert class_projection["snapshot_count"] == 1

    subject_projection = get_subject_teacher_analytics_projection(
        actor=teacher_user,
        tenant=school,
        learning_area_id=assessment.learning_area_id,
    )
    assert subject_projection["projection_type"] == "subject_teacher"
    assert subject_projection["snapshot_count"] == 1

    parent_projection = get_future_parent_snapshot_projection(
        actor=teacher_user,
        tenant=school,
        learner_id=enrolled_student.id,
    )
    assert parent_projection["ready_for_release"] is False
    assert parent_projection["learner_snapshots"] == []
