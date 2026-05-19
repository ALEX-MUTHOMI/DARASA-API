from __future__ import annotations

import uuid

import pytest
from django.utils import timezone

from academics.models import TeacherAssignment
from core.models import CustomUser, Role, TenantUserRole
from grading.services import (
    compile_assessment,
    get_deputy_academics_readiness_projection,
    get_future_parent_report_readiness_projection,
    get_hod_readiness_projection,
    get_principal_readiness_projection,
    get_teacher_readiness_projection,
    submit_grade_batch,
)


pytestmark = [pytest.mark.django_db, pytest.mark.phase6, pytest.mark.grading]


def _confirmation(actor, tenant):
    return {
        "actor_id": actor.id,
        "tenant_id": tenant.id,
        "method": "session_step_up",
        "confirmed_at": timezone.now(),
        "confirmation_reference": "session-step-up:phase6d-role",
    }


def _role_user(school, role_code):
    role = Role.objects.get_or_create(
        code=role_code,
        defaults={"name": role_code.replace("_", " ").title()},
    )[0]
    user = CustomUser.objects.create_user(
        email=f"phase6d-{role_code}-{uuid.uuid4().hex[:8]}@example.test",
        password="test-only-secret",
    )
    TenantUserRole.objects.create(tenant=school, user=user, role=role)
    return user


def _compiled_assessment(school, assessment, teacher_user, principal_user, student):
    submit_grade_batch(
        actor=teacher_user,
        tenant=school,
        assessment_id=assessment.id,
        payload={"rows": [{"student_id": str(student.id), "raw_score": "86.00"}]},
        idempotency_key=f"phase6d-role-submit-{assessment.id}",
        confirmation=_confirmation(teacher_user, school),
    )
    return compile_assessment(
        tenant=school,
        assessment_id=assessment.id,
        requested_by=principal_user,
    )


def test_teacher_readiness_projection_is_assignment_scoped(
    school,
    other_school,
    assessment,
    teacher_user,
    teacher_assignment,
    principal_user,
    enrolled_student,
):
    _compiled_assessment(
        school,
        assessment,
        teacher_user,
        principal_user,
        enrolled_student,
    )
    unassigned_teacher = _role_user(school, Role.RoleCode.SUBJECT_TEACHER.value)

    projection = get_teacher_readiness_projection(
        actor=teacher_user,
        tenant=school,
        assessment_id=assessment.id,
    )
    denied = get_teacher_readiness_projection(
        actor=unassigned_teacher,
        tenant=school,
        assessment_id=assessment.id,
    )
    cross_tenant = get_teacher_readiness_projection(
        actor=teacher_user,
        tenant=other_school,
    )

    assert projection["projection_type"] == "teacher"
    assert projection["assessment_count"] == 1
    assert projection["assessments"][0]["assessment_id"] == str(assessment.id)
    assert denied["assessments"] == []
    assert cross_tenant["assessments"] == []


def test_hod_deputy_and_principal_readiness_scopes_are_role_bounded(
    school,
    other_school,
    assessment,
    teacher_user,
    teacher_assignment,
    principal_user,
    enrolled_student,
):
    _compiled_assessment(
        school,
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
        academic_year=assessment.academic_year,
        term=assessment.term,
    )
    deputy = _role_user(school, Role.RoleCode.DEPUTY_PRINCIPAL.value)

    assert (
        get_hod_readiness_projection(actor=hod, tenant=school)["assessment_count"]
        == 1
    )
    assert (
        get_deputy_academics_readiness_projection(actor=deputy, tenant=school)[
            "assessment_count"
        ]
        == 1
    )
    assert (
        get_principal_readiness_projection(actor=principal_user, tenant=school)[
            "assessment_count"
        ]
        == 1
    )
    assert (
        get_principal_readiness_projection(actor=principal_user, tenant=other_school)[
            "assessment_count"
        ]
        == 0
    )


def test_hod_readiness_fails_closed_without_department_assignment(
    school,
    assessment,
    teacher_user,
    teacher_assignment,
    principal_user,
    enrolled_student,
):
    _compiled_assessment(
        school,
        assessment,
        teacher_user,
        principal_user,
        enrolled_student,
    )
    hod = _role_user(school, Role.RoleCode.HOD.value)

    projection = get_hod_readiness_projection(actor=hod, tenant=school)

    assert projection["assessments"] == []


def test_future_parent_readiness_projection_fails_closed(
    school,
    assessment,
    teacher_user,
    teacher_assignment,
    principal_user,
    enrolled_student,
):
    _compiled_assessment(
        school,
        assessment,
        teacher_user,
        principal_user,
        enrolled_student,
    )
    guardian = _role_user(school, Role.RoleCode.GUARDIAN.value)

    projection = get_future_parent_report_readiness_projection(
        actor=guardian,
        tenant=school,
        learner_id=enrolled_student.id,
    )

    assert projection["projection_type"] == "future_parent"
    assert not projection["ready_for_release"]
    assert projection["assessments"] == []
