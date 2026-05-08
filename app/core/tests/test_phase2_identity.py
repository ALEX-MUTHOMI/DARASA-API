from __future__ import annotations

import uuid

import pytest
from django.db import IntegrityError, transaction

from core.models import CustomUser, Role, TenantUserRole
from core.policies import PolicyContext, is_allowed
from core.selectors import (
    get_active_tenant_user_role_bindings,
    get_principal_role,
    get_roles_for_user_in_tenant,
    user_has_role_in_tenant,
)
from core.services import ensure_default_roles
from tenant.models import School


pytestmark = [pytest.mark.django_db, pytest.mark.phase2]


def _school(label: str) -> School:
    token = uuid.uuid4().hex[:10]
    return School.objects.create(
        name=f"{label} School {token}",
        schema_name=f"sch_{token}",
        subdomain=f"{label.lower()}-{token}",
        school_code=f"SCH{token[:9]}".upper(),
    )


def _user(email: str = "actor@example.test") -> CustomUser:
    return CustomUser.objects.create_user(email=email, password="test-only-secret")


def test_default_roles_are_seeded_with_unique_codes():
    roles = ensure_default_roles()

    assert {role.code for role in roles} == {choice.value for choice in Role.RoleCode}
    assert Role.objects.filter(code=Role.RoleCode.PRINCIPAL).count() == 1
    assert get_principal_role().code == Role.RoleCode.PRINCIPAL


def test_identity_and_rbac_models_use_uuid_primary_keys():
    school = _school("uuid")
    user = _user("uuid-user@example.test")
    role = Role.objects.create(code=Role.RoleCode.AUDITOR, name="Auditor")
    binding = TenantUserRole.objects.create(
        tenant=school,
        user=user,
        role=role,
        assigned_by=user,
    )

    assert isinstance(school.pk, uuid.UUID)
    assert isinstance(user.pk, uuid.UUID)
    assert isinstance(role.pk, uuid.UUID)
    assert isinstance(binding.pk, uuid.UUID)


def test_tenant_user_role_binding_is_tenant_scoped_and_fail_closed():
    school_a = _school("alpha")
    school_b = _school("beta")
    user = _user("teacher@example.test")
    role = Role.objects.create(
        code=Role.RoleCode.SUBJECT_TEACHER,
        name="Subject Teacher",
    )

    TenantUserRole.objects.create(tenant=school_a, user=user, role=role)

    assert user_has_role_in_tenant(
        user=user,
        tenant=school_a,
        role_code=Role.RoleCode.SUBJECT_TEACHER,
    )
    assert not user_has_role_in_tenant(
        user=user,
        tenant=school_b,
        role_code=Role.RoleCode.SUBJECT_TEACHER,
    )
    assert not user_has_role_in_tenant(
        user=user,
        tenant=None,
        role_code=Role.RoleCode.SUBJECT_TEACHER,
    )


def test_same_user_can_hold_roles_in_different_tenants():
    school_a = _school("north")
    school_b = _school("south")
    user = _user("multi-tenant@example.test")
    role = Role.objects.create(code=Role.RoleCode.HOD, name="HOD")

    TenantUserRole.objects.create(tenant=school_a, user=user, role=role)
    TenantUserRole.objects.create(tenant=school_b, user=user, role=role)

    assert get_roles_for_user_in_tenant(user=user, tenant=school_a).count() == 1
    assert get_roles_for_user_in_tenant(user=user, tenant=school_b).count() == 1


def test_duplicate_active_tenant_role_binding_is_rejected():
    school = _school("dup")
    user = _user("duplicate@example.test")
    role = Role.objects.create(code=Role.RoleCode.GUARDIAN, name="Guardian")
    TenantUserRole.objects.create(tenant=school, user=user, role=role)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            TenantUserRole.objects.create(tenant=school, user=user, role=role)


def test_inactive_binding_is_ignored_by_selectors_and_policies():
    school = _school("inactive")
    user = _user("inactive-binding@example.test")
    role = Role.objects.create(code=Role.RoleCode.AUDITOR, name="Auditor")
    TenantUserRole.objects.create(
        tenant=school,
        user=user,
        role=role,
        is_active=False,
    )

    context = PolicyContext(
        tenant=school,
        actor=user,
        action="tenant.admin",
        role=role,
    )

    assert get_active_tenant_user_role_bindings(user=user, tenant=school).count() == 0
    assert not is_allowed(context)


def test_policy_context_denies_missing_or_unknown_context():
    school = _school("policy")
    user = _user("policy@example.test")
    role = Role.objects.create(code=Role.RoleCode.PRINCIPAL, name="Principal")

    assert not is_allowed(
        PolicyContext(tenant=None, actor=user, action="tenant.admin", role=role)
    )
    assert not is_allowed(
        PolicyContext(tenant=school, actor=None, action="tenant.admin", role=role)
    )
    assert not is_allowed(
        PolicyContext(tenant=school, actor=user, action="tenant.admin", role=None)
    )
    assert not is_allowed(
        PolicyContext(tenant=school, actor=user, action="unknown", role=role)
    )
