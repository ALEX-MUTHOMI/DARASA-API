from __future__ import annotations

import pathlib
import uuid

import pytest
from django.core.exceptions import ValidationError

from core.models import CustomUser, Role, TenantUserRole
from tenant.models import Domain, School
from tenant.selectors import get_school_by_domain, get_school_by_schema
from tenant.services import TenantProvisioningService


pytestmark = [pytest.mark.django_db, pytest.mark.phase2]


def _domain(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}.school.test"


def test_phase2_migrations_exist_for_tenant_and_core():
    app_root = pathlib.Path(__file__).resolve().parents[2]

    assert (app_root / "tenant" / "migrations" / "0001_initial.py").exists()
    assert (app_root / "core" / "migrations" / "0001_initial.py").exists()


def test_successful_school_admin_provisioning_creates_required_graph():
    context = TenantProvisioningService.provision_school_and_admin(
        school_name="Nairobi Test Academy",
        domain_string=_domain("nairobi"),
        admin_email="Principal@Example.TEST",
        admin_password="test-only-secret",
    )

    assert isinstance(context.school.pk, uuid.UUID)
    assert isinstance(context.domain.pk, uuid.UUID)
    assert isinstance(context.principal.pk, uuid.UUID)
    assert context.principal.email == "principal@example.test"
    assert context.principal.check_password("test-only-secret")
    assert context.role_binding.tenant == context.school
    assert context.role_binding.role.code == Role.RoleCode.PRINCIPAL
    assert get_school_by_domain(context.domain.domain) == context.school
    assert get_school_by_schema(context.school.schema_name) == context.school


def test_duplicate_domain_is_rejected_without_partial_records():
    domain = _domain("duplicate")
    TenantProvisioningService.provision_school_and_admin(
        school_name="First School",
        domain_string=domain,
        admin_email="first@example.test",
        admin_password="test-only-secret",
    )
    counts = (
        School.objects.count(),
        Domain.objects.count(),
        CustomUser.objects.count(),
        TenantUserRole.objects.count(),
    )

    with pytest.raises(ValueError) as exc:
        TenantProvisioningService.provision_school_and_admin(
            school_name="Second School",
            domain_string=domain.upper(),
            admin_email="second@example.test",
            admin_password="test-only-secret",
        )

    assert "test-only-secret" not in str(exc.value)
    assert (
        School.objects.count(),
        Domain.objects.count(),
        CustomUser.objects.count(),
        TenantUserRole.objects.count(),
    ) == counts


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("school_name", " "),
        ("domain_string", "not a valid domain"),
        ("domain_string", "bad_domain.example.test"),
        ("domain_string", "\u2603.school.test"),
        ("domain_string", "https://evil.example.test/path"),
        ("domain_string", "www.example.test"),
        ("admin_email", " "),
        ("admin_email", "invalid-email"),
        ("admin_password", " "),
    ],
)
def test_invalid_provisioning_input_fails_closed(field, value):
    payload = {
        "school_name": "Secure Test School",
        "domain_string": _domain("secure"),
        "admin_email": "admin@example.test",
        "admin_password": "test-only-secret",
    }
    payload[field] = value

    with pytest.raises(ValueError) as exc:
        TenantProvisioningService.provision_school_and_admin(**payload)

    assert "test-only-secret" not in str(exc.value)
    assert School.objects.count() == 0
    assert Domain.objects.count() == 0
    assert CustomUser.objects.count() == 0


@pytest.mark.parametrize(
    "domain",
    [
        "www.darasa.test",
        "admin.darasa.test",
        "api.darasa.com",
        "app.darasa.test",
        "sys.darasa.test",
    ],
)
def test_domain_model_rejects_reserved_leftmost_labels(domain):
    with pytest.raises(ValidationError):
        Domain(domain=domain).clean()


@pytest.mark.parametrize("subdomain", ["www", "admin", "api", "app", "sys"])
def test_school_model_rejects_reserved_subdomains(subdomain):
    with pytest.raises(ValidationError):
        School(
            name="Reserved Prefix School",
            schema_name=f"sch_{uuid.uuid4().hex[:10]}",
            subdomain=subdomain,
            school_code=f"SCH{uuid.uuid4().hex[:9]}".upper(),
        ).clean()


def test_duplicate_subdomain_is_rejected():
    first = TenantProvisioningService.provision_school_and_admin(
        school_name="Subdomain One",
        domain_string="shared-one.school.test",
        admin_email="subdomain-one@example.test",
        admin_password="test-only-secret",
    )

    with pytest.raises(ValueError):
        TenantProvisioningService.provision_school_and_admin(
            school_name="Subdomain Two",
            domain_string="shared-one.other.test",
            admin_email="subdomain-two@example.test",
            admin_password="test-only-secret",
        )

    assert School.objects.filter(subdomain=first.school.subdomain).count() == 1


def test_failed_provisioning_rolls_back_created_records(monkeypatch):
    def fail_create_user(*args, **kwargs):
        raise RuntimeError("downstream identity failure")

    monkeypatch.setattr(CustomUser.objects, "create_user", fail_create_user)

    with pytest.raises(RuntimeError):
        TenantProvisioningService.provision_school_and_admin(
            school_name="Rollback School",
            domain_string=_domain("rollback"),
            admin_email="rollback@example.test",
            admin_password="test-only-secret",
        )

    assert School.objects.count() == 0
    assert Domain.objects.count() == 0
    assert CustomUser.objects.count() == 0


def test_principal_role_is_reused_safely():
    role = Role.objects.create(
        code=Role.RoleCode.PRINCIPAL,
        name=Role.RoleCode.PRINCIPAL.label,
        description="Existing principal capability.",
    )

    context = TenantProvisioningService.provision_school_and_admin(
        school_name="Role Reuse School",
        domain_string=_domain("reuse"),
        admin_email="reuse@example.test",
        admin_password="test-only-secret",
    )

    assert context.role_binding.role == role
    assert Role.objects.filter(code=Role.RoleCode.PRINCIPAL).count() == 1


def test_tenant_lookup_is_case_insensitive_and_safe_for_invalid_input():
    context = TenantProvisioningService.provision_school_and_admin(
        school_name="Lookup School",
        domain_string="Lookup.school.test",
        admin_email="lookup@example.test",
        admin_password="test-only-secret",
    )

    assert get_school_by_domain("LOOKUP.SCHOOL.TEST") == context.school
    assert get_school_by_domain(" ") is None
    assert get_school_by_schema("missing_schema") is None
