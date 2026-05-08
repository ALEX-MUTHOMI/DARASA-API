from __future__ import annotations

from academics.models import TeacherAssignment
from core.models import Role
from core.policies import PolicyContext
from core.selectors import user_has_role_in_tenant
from curriculum.models import CurriculumLearningArea, SpecificLearningOutcome


CURRICULUM_MANAGE_ROLES = frozenset(
    {
        Role.RoleCode.PRINCIPAL.value,
        Role.RoleCode.SCHOOL_ADMIN.value,
    }
)

CURRICULUM_VIEW_ROLES = frozenset(
    {
        Role.RoleCode.PRINCIPAL.value,
        Role.RoleCode.SCHOOL_ADMIN.value,
        Role.RoleCode.HOD.value,
        Role.RoleCode.CLASS_TEACHER.value,
        Role.RoleCode.SUBJECT_TEACHER.value,
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


def _is_manager(context: PolicyContext) -> bool:
    return _context_is_valid(context) and context.role.code in CURRICULUM_MANAGE_ROLES


def _can_view_learning_area(
    context: PolicyContext,
    curriculum_learning_area: CurriculumLearningArea,
) -> bool:
    if not _context_is_valid(context):
        return False
    learning_area = curriculum_learning_area.learning_area
    if learning_area.tenant_id != context.tenant.id:
        return False
    if context.role.code in CURRICULUM_MANAGE_ROLES:
        return True
    if context.role.code not in CURRICULUM_VIEW_ROLES:
        return False
    return TeacherAssignment.objects.filter(
        tenant=context.tenant,
        teacher=context.actor,
        learning_area=learning_area,
        is_active=True,
        learning_area__is_active=True,
    ).exists()


def can_view_curriculum_map(
    context: PolicyContext,
    *,
    curriculum_learning_area: CurriculumLearningArea,
) -> bool:
    return _can_view_learning_area(context, curriculum_learning_area)


def can_manage_curriculum_source_documents(context: PolicyContext) -> bool:
    return (
        context.action == "curriculum.manage_source"
        and _is_manager(context)
    )


def can_activate_curriculum_version(context: PolicyContext) -> bool:
    return (
        context.action == "curriculum.activate_version"
        and _is_manager(context)
    )


def can_create_curriculum_structure(context: PolicyContext) -> bool:
    return (
        context.action == "curriculum.create_structure"
        and _is_manager(context)
    )


def can_view_rubric_foundation(
    context: PolicyContext,
    *,
    learning_outcome: SpecificLearningOutcome,
) -> bool:
    curriculum_learning_area = (
        learning_outcome.sub_strand.strand.curriculum_learning_area
    )
    return (
        context.action == "curriculum.view_rubric_foundation"
        and _can_view_learning_area(context, curriculum_learning_area)
    )
