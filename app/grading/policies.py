"""Fail-closed grading ABAC policies.

Grades are academic records.  A tenant role proves broad capability, while an
active teacher assignment proves contextual authority for a cohort and learning
area.
"""

from __future__ import annotations

from typing import Any

from academics.models import TeacherAssignment
from core.models import Role
from core.policies import PolicyContext
from core.selectors import user_has_role_in_tenant
from grading.models import Assessment, GradeCorrectionRequest, GradeRecord


GRADING_ADMIN_ROLES = frozenset(
    {
        Role.RoleCode.PRINCIPAL.value,
        Role.RoleCode.SCHOOL_ADMIN.value,
        Role.RoleCode.HOD.value,
    }
)
GRADING_TEACHER_ROLES = frozenset(
    {
        Role.RoleCode.SUBJECT_TEACHER.value,
        Role.RoleCode.CLASS_TEACHER.value,
        Role.RoleCode.HOD.value,
    }
)


def _context_is_valid(context: PolicyContext) -> bool:
    if context.tenant is None:
        return False
    if context.actor is None or not context.actor.is_active:
        return False
    if context.role is None or not context.role.is_active:
        return False
    if not context.action:
        return False
    return user_has_role_in_tenant(
        user=context.actor,
        tenant=context.tenant,
        role_code=context.role.code,
    )


def _in_tenant(context: PolicyContext, resource: Any) -> bool:
    return (
        context.tenant is not None
        and getattr(resource, "tenant_id", None) == context.tenant.id
    )


def _is_admin(context: PolicyContext) -> bool:
    return _context_is_valid(context) and context.role.code in GRADING_ADMIN_ROLES


def _has_assignment_for_assessment(
    context: PolicyContext,
    *,
    assessment: Assessment,
) -> bool:
    if not _context_is_valid(context) or context.role.code not in GRADING_TEACHER_ROLES:
        return False
    if not _in_tenant(context, assessment):
        return False
    return TeacherAssignment.objects.filter(
        tenant=context.tenant,
        teacher=context.actor,
        cohort=assessment.cohort,
        learning_area=assessment.learning_area,
        academic_year=assessment.academic_year,
        term=assessment.term,
        is_active=True,
        cohort__is_active=True,
        learning_area__is_active=True,
    ).exists()


def can_view_grading_context(context: PolicyContext, *, assessment: Assessment) -> bool:
    if not _in_tenant(context, assessment):
        return False
    return _is_admin(context) or _has_assignment_for_assessment(
        context,
        assessment=assessment,
    )


def can_view_assessment(context: PolicyContext, *, assessment: Assessment) -> bool:
    return context.action == "grading.assessment.view" and can_view_grading_context(
        context,
        assessment=assessment,
    )


def can_enter_grades(context: PolicyContext, *, assessment: Assessment) -> bool:
    if context.action != "grading.grades.enter":
        return False
    if assessment.status != Assessment.Status.OPEN:
        return False
    return _has_assignment_for_assessment(context, assessment=assessment)


def can_submit_grade_batch(context: PolicyContext, *, assessment: Assessment) -> bool:
    return context.action == "grading.batch.submit" and can_enter_grades(
        PolicyContext(
            tenant=context.tenant,
            actor=context.actor,
            action="grading.grades.enter",
            role=context.role,
        ),
        assessment=assessment,
    )


def can_view_grade_records(
    context: PolicyContext,
    *,
    grade_record: GradeRecord,
) -> bool:
    if context.action != "grading.records.view":
        return False
    if not _in_tenant(context, grade_record):
        return False
    return _is_admin(context) or _has_assignment_for_assessment(
        context,
        assessment=grade_record.assessment,
    )


def can_request_grade_correction(
    context: PolicyContext,
    *,
    grade_record: GradeRecord,
) -> bool:
    if context.action != "grading.correction.request":
        return False
    return can_view_grade_records(
        PolicyContext(
            tenant=context.tenant,
            actor=context.actor,
            action="grading.records.view",
            role=context.role,
        ),
        grade_record=grade_record,
    )


def can_review_grade_correction(
    context: PolicyContext,
    *,
    correction: GradeCorrectionRequest,
) -> bool:
    if context.action != "grading.correction.review":
        return False
    if not _in_tenant(context, correction):
        return False
    if correction.requested_by_id == getattr(context.actor, "id", None):
        return False
    return _is_admin(context)


def can_view_grade_completion_summary(
    context: PolicyContext,
    *,
    assessment: Assessment,
) -> bool:
    if context.action != "grading.summary.view":
        return False
    if not _in_tenant(context, assessment):
        return False
    return _is_admin(context)
