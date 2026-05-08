from __future__ import annotations

from django.db.models import QuerySet

from core.models import CustomUser, Role, TenantUserRole
from tenant.models import School


def get_active_tenant_user_role_bindings(
    *,
    user: CustomUser | None = None,
    tenant: School | None = None,
) -> QuerySet[TenantUserRole]:
    if user is None and tenant is None:
        raise ValueError("Either user or tenant is required.")

    queryset = TenantUserRole.objects.filter(
        is_active=True,
        role__is_active=True,
        user__is_active=True,
        tenant__is_active=True,
    ).select_related("tenant", "user", "role")
    if user is not None:
        queryset = queryset.filter(user=user)
    if tenant is not None:
        queryset = queryset.filter(tenant=tenant)
    return queryset


def get_roles_for_user_in_tenant(
    *,
    user: CustomUser | None,
    tenant: School | None,
) -> QuerySet[Role]:
    if user is None or tenant is None:
        return Role.objects.none()
    role_ids = get_active_tenant_user_role_bindings(
        user=user,
        tenant=tenant,
    ).values("role_id")
    return Role.objects.filter(id__in=role_ids, is_active=True)


def user_has_role_in_tenant(
    *,
    user: CustomUser | None,
    tenant: School | None,
    role_code: str,
) -> bool:
    if user is None or tenant is None or not role_code:
        return False
    return get_roles_for_user_in_tenant(user=user, tenant=tenant).filter(
        code=role_code,
    ).exists()


def get_principal_role() -> Role | None:
    return Role.objects.filter(code=Role.RoleCode.PRINCIPAL, is_active=True).first()
