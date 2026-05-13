"""Fail-closed curriculum and CCT policy helpers.

RBAC grants only broad capability; these helpers still require a tenant-bound
actor, an active role binding, and the exact action being checked.  Unknown
actions and missing context always deny.
"""

from __future__ import annotations

from academics.models import TeacherAssignment
from core.models import Role
from core.policies import PolicyContext
from core.selectors import user_has_role_in_tenant
from curriculum.models import (
    CurriculumLearningArea,
    PrincipalNotificationEvidenceCard,
    SpecificLearningOutcome,
)


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


def can_view_source_registry(context: PolicyContext) -> bool:
    return (
        context.action == "curriculum.cct.register_source"
        and _context_is_valid(context)
        and context.role.code in CURRICULUM_VIEW_ROLES
    )


def can_register_curriculum_source(context: PolicyContext) -> bool:
    return (
        context.action == "curriculum.cct.register_source"
        and _is_manager(context)
    )


def can_approve_curriculum_source(context: PolicyContext) -> bool:
    return (
        context.action == "curriculum.cct.approve_source"
        and _is_manager(context)
    )


def can_approve_change_set(context: PolicyContext) -> bool:
    return (
        context.action == "curriculum.cct.approve_change_set"
        and _is_manager(context)
    )


def can_reject_change_set(context: PolicyContext) -> bool:
    return (
        context.action == "curriculum.cct.reject_change_set"
        and _is_manager(context)
    )


def can_publish_curriculum_version(context: PolicyContext) -> bool:
    return (
        context.action == "curriculum.cct.publish_version"
        and _is_manager(context)
    )


def can_supersede_curriculum_version(context: PolicyContext) -> bool:
    return (
        context.action == "curriculum.cct.supersede_version"
        and _is_manager(context)
    )


def can_view_regulatory_notice(context: PolicyContext) -> bool:
    return (
        context.action == "curriculum.regulatory.view"
        and _context_is_valid(context)
        and context.role.code in CURRICULUM_VIEW_ROLES
    )


def can_register_regulatory_notice(context: PolicyContext) -> bool:
    return (
        context.action == "curriculum.regulatory.register"
        and _is_manager(context)
    )


def can_review_regulatory_notice(context: PolicyContext) -> bool:
    return (
        context.action == "curriculum.regulatory.review"
        and _is_manager(context)
    )


def can_classify_regulatory_notice(context: PolicyContext) -> bool:
    return (
        context.action == "curriculum.regulatory.classify"
        and _is_manager(context)
    )


def can_create_impact_analysis(context: PolicyContext) -> bool:
    return (
        context.action == "curriculum.regulatory.create_impact"
        and _is_manager(context)
    )


def can_issue_principal_notification(context: PolicyContext) -> bool:
    return (
        context.action == "curriculum.notification.issue"
        and _is_manager(context)
    )


def can_acknowledge_principal_notification(
    context: PolicyContext,
    *,
    evidence_card: PrincipalNotificationEvidenceCard,
) -> bool:
    return (
        context.action == "curriculum.notification.acknowledge"
        and _is_manager(context)
        and evidence_card.tenant_id == context.tenant.id
    )


def can_view_teacher_readiness_requirement(context: PolicyContext) -> bool:
    return (
        context.action == "curriculum.teacher_readiness.view"
        and _context_is_valid(context)
        and context.role.code in CURRICULUM_VIEW_ROLES
    )
