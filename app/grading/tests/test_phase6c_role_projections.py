from __future__ import annotations

from django.utils import timezone
import pytest

from academics.models import TeacherAssignment
from core.models import CustomUser, Role, TenantUserRole
from grading.services import (
    compile_assessment,
    get_deputy_academics_projection,
    get_future_parent_learner_projection,
    get_hod_compilation_projection,
    get_principal_compilation_projection,
    get_teacher_compilation_projection,
    submit_grade_batch,
)


pytestmark = [pytest.mark.django_db, pytest.mark.phase6]


def _confirmation(actor, tenant):
    return {
        "actor_id": actor.id,
        "tenant_id": tenant.id,
        "method": "session_step_up",
        "confirmed_at": timezone.now(),
        "confirmation_reference": "session-step-up:projection",
    }


def _create_role_user(school, code):
    role = Role.objects.get_or_create(
        code=code,
        defaults={"name": code.replace("_", " ").title()},
    )[0]
    user = CustomUser.objects.create_user(
        email=f"phase6c-{code}-{school.id}@example.test",
        password="test-only-secret",
    )
    TenantUserRole.objects.create(tenant=school, user=user, role=role)
    return user


def _compiled_run(school, assessment, teacher_user, principal_user, enrolled_student):
    submit_grade_batch(
        actor=teacher_user,
        tenant=school,
        assessment_id=assessment.id,
        payload={"rows": [{"student_id": str(enrolled_student.id), "raw_score": "80"}]},
        idempotency_key="projection-submit",
        confirmation=_confirmation(teacher_user, school),
    )
    return compile_assessment(
        tenant=school,
        assessment_id=assessment.id,
        requested_by=principal_user,
    )


def test_teacher_projection_is_assignment_scoped(
    school,
    assessment,
    teacher_user,
    teacher_assignment,
    principal_user,
    enrolled_student,
):
    _compiled_run(school, assessment, teacher_user, principal_user, enrolled_student)

    projection = get_teacher_compilation_projection(
        actor=teacher_user,
        tenant=school,
        assessment_id=assessment.id,
    )

    assert projection["projection_type"] == "teacher"
    assert len(projection["summaries"]) == 1
    assert projection["summaries"][0]["assessment_id"] == str(assessment.id)


def test_hod_deputy_and_principal_projection_are_role_and_tenant_scoped(
    school,
    other_school,
    assessment,
    teacher_user,
    teacher_assignment,
    principal_user,
    enrolled_student,
):
    _compiled_run(school, assessment, teacher_user, principal_user, enrolled_student)
    hod = _create_role_user(school, Role.RoleCode.HOD.value)
    TeacherAssignment.objects.create(
        tenant=school,
        teacher=hod,
        cohort=assessment.cohort,
        learning_area=assessment.learning_area,
        academic_year=assessment.academic_year,
        term=assessment.term,
    )
    deputy = _create_role_user(school, Role.RoleCode.DEPUTY_PRINCIPAL.value)

    assert get_hod_compilation_projection(actor=hod, tenant=school)["summaries"]
    assert get_deputy_academics_projection(actor=deputy, tenant=school)["summaries"]
    assert get_principal_compilation_projection(
        actor=principal_user,
        tenant=school,
    )["summaries"]
    assert not get_principal_compilation_projection(
        actor=principal_user,
        tenant=other_school,
    )["summaries"]


def test_hod_projection_fails_closed_without_assignment(
    school,
    assessment,
    teacher_user,
    teacher_assignment,
    principal_user,
    enrolled_student,
):
    _compiled_run(school, assessment, teacher_user, principal_user, enrolled_student)
    hod = _create_role_user(school, Role.RoleCode.HOD.value)

    projection = get_hod_compilation_projection(actor=hod, tenant=school)

    assert projection["summaries"] == []


def test_future_parent_projection_fails_closed_without_guardian_role(
    school,
    assessment,
    teacher_user,
    teacher_assignment,
    principal_user,
    enrolled_student,
):
    _compiled_run(school, assessment, teacher_user, principal_user, enrolled_student)

    projection = get_future_parent_learner_projection(
        actor=teacher_user,
        tenant=school,
        learner_id=enrolled_student.id,
    )

    assert projection["projection_type"] == "future_parent"
    assert projection["learner_snapshots"] == []


def test_future_parent_projection_fails_closed_even_with_guardian_role(
    school,
    assessment,
    teacher_user,
    teacher_assignment,
    principal_user,
    enrolled_student,
):
    _compiled_run(school, assessment, teacher_user, principal_user, enrolled_student)
    guardian = _create_role_user(school, Role.RoleCode.GUARDIAN.value)

    projection = get_future_parent_learner_projection(
        actor=guardian,
        tenant=school,
        learner_id=enrolled_student.id,
    )

    assert projection["learner_snapshots"] == []
