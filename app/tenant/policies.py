from __future__ import annotations

from core.models import CustomUser, Role
from core.policies import PolicyContext, is_allowed
from tenant.models import School


def can_administer_tenant(
    *,
    actor: CustomUser | None,
    tenant: School | None,
    role: Role | None,
) -> bool:
    return is_allowed(
        PolicyContext(
            tenant=tenant,
            actor=actor,
            action="tenant.admin",
            role=role,
        )
    )
