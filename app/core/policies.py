from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from django.utils import timezone

from core.models import CustomUser, Role
from core.selectors import user_has_role_in_tenant
from tenant.models import School


@dataclass(frozen=True)
class PolicyContext:
    tenant: School | None
    actor: CustomUser | None
    action: str
    resource: Any = None
    role: Role | None = None
    timestamp: datetime = field(default_factory=timezone.now)
    request_metadata: dict[str, Any] = field(default_factory=dict)


def is_allowed(context: PolicyContext) -> bool:
    if context.tenant is None:
        return False
    if context.actor is None or not context.actor.is_active:
        return False
    if context.role is None or not context.role.is_active:
        return False
    if not context.action:
        return False
    if context.action not in {"tenant.admin"}:
        return False
    return user_has_role_in_tenant(
        user=context.actor,
        tenant=context.tenant,
        role_code=context.role.code,
    )
