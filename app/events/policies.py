"""Fail-closed event operations policies."""

from __future__ import annotations

from core.models import Role
from core.policies import PolicyContext
from core.selectors import user_has_role_in_tenant


EVENT_ADMIN_ROLES = frozenset(
    {
        Role.RoleCode.PRINCIPAL.value,
        Role.RoleCode.SCHOOL_ADMIN.value,
        Role.RoleCode.AUDITOR.value,
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


def _can_operate_events(context: PolicyContext) -> bool:
    return _context_is_valid(context) and context.role.code in EVENT_ADMIN_ROLES


def can_view_audit_events(context: PolicyContext) -> bool:
    return context.action == "events.audit.view" and _can_operate_events(context)


def can_view_event_backlog(context: PolicyContext) -> bool:
    return context.action == "events.backlog.view" and _can_operate_events(context)


def can_view_dead_letter_events(context: PolicyContext) -> bool:
    return context.action == "events.dead_letter.view" and _can_operate_events(context)


def can_replay_dead_letter_event(context: PolicyContext) -> bool:
    return (
        context.action == "events.dead_letter.replay"
        and _can_operate_events(context)
    )


def can_inspect_event_payload_metadata(context: PolicyContext) -> bool:
    return context.action == "events.payload_metadata.view" and _can_operate_events(
        context
    )


def can_register_event_type(context: PolicyContext) -> bool:
    return context.action == "events.registry.register" and _can_operate_events(context)


def can_deactivate_event_type(context: PolicyContext) -> bool:
    return context.action == "events.registry.deactivate" and _can_operate_events(
        context
    )
