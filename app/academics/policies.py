from __future__ import annotations

from academics.models import Cohort, LearningArea, Student, TeacherAssignment
from core.models import Role
from core.policies import PolicyContext
from core.selectors import user_has_role_in_tenant


ACADEMIC_ADMIN_ROLES = frozenset(
    {
        Role.RoleCode.PRINCIPAL.value,
        Role.RoleCode.SCHOOL_ADMIN.value,
    }
)

ACADEMIC_TEACHER_ROLES = frozenset(
    {
        Role.RoleCode.CLASS_TEACHER.value,
        Role.RoleCode.SUBJECT_TEACHER.value,
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


def _resource_in_tenant(context: PolicyContext, resource) -> bool:
    tenant = context.tenant
    return tenant is not None and getattr(resource, "tenant_id", None) == tenant.id


def _is_academic_admin(context: PolicyContext) -> bool:
    return _context_is_valid(context) and context.role.code in ACADEMIC_ADMIN_ROLES


def _has_active_assignment(
    context: PolicyContext,
    *,
    cohort: Cohort,
    learning_area: LearningArea | None = None,
) -> bool:
    if (
        not _context_is_valid(context)
        or context.role.code not in ACADEMIC_TEACHER_ROLES
    ):
        return False
    if not _resource_in_tenant(context, cohort):
        return False
    filters = {
        "tenant": context.tenant,
        "teacher": context.actor,
        "cohort": cohort,
        "is_active": True,
        "cohort__is_active": True,
    }
    if learning_area is not None:
        if not _resource_in_tenant(context, learning_area):
            return False
        filters["learning_area"] = learning_area
        filters["learning_area__is_active"] = True
    return TeacherAssignment.objects.filter(**filters).exists()


def can_view_cohort_roster(
    context: PolicyContext,
    *,
    cohort: Cohort,
    learning_area: LearningArea | None = None,
) -> bool:
    if not _resource_in_tenant(context, cohort):
        return False
    if learning_area is not None and not _resource_in_tenant(context, learning_area):
        return False
    if _is_academic_admin(context):
        return True
    return _has_active_assignment(
        context,
        cohort=cohort,
        learning_area=learning_area,
    )


def can_view_learner_academic_profile(
    context: PolicyContext,
    *,
    learner: Student,
) -> bool:
    if not _resource_in_tenant(context, learner):
        return False
    if _is_academic_admin(context):
        return True
    if not _context_is_valid(context):
        return False
    return TeacherAssignment.objects.filter(
        tenant=context.tenant,
        teacher=context.actor,
        cohort__enrollments__student=learner,
        cohort__enrollments__is_active=True,
        is_active=True,
        cohort__is_active=True,
    ).exists()


def can_manage_cohort(context: PolicyContext, *, cohort: Cohort) -> bool:
    return _resource_in_tenant(context, cohort) and _is_academic_admin(context)


def can_assign_teacher(context: PolicyContext, *, cohort: Cohort) -> bool:
    return _resource_in_tenant(context, cohort) and _is_academic_admin(context)


def can_teacher_access_learning_area(
    context: PolicyContext,
    *,
    cohort: Cohort,
    learning_area: LearningArea,
) -> bool:
    return _has_active_assignment(
        context,
        cohort=cohort,
        learning_area=learning_area,
    )
