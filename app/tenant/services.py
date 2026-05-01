from __future__ import annotations

import uuid
from dataclasses import dataclass
from urllib.parse import urlparse

from django.db import transaction
from django.utils.text import slugify
from django_tenants.utils import get_public_schema_name, schema_context

from core.models import CustomUser, Role, TenantUserRole
from tenant.models import Domain, School


@dataclass(frozen=True)
class ProvisionedTenantContext:
    school: School
    domain: Domain
    principal: CustomUser
    role_binding: TenantUserRole


class TenantProvisioningService:
    @classmethod
    def provision_school_and_admin(
        cls,
        *,
        school_name: str,
        domain_string: str,
        admin_email: str,
        admin_password: str,
    ) -> ProvisionedTenantContext:
        assert school_name, "school_name is required"
        assert domain_string, "domain_string is required"
        assert admin_email, "admin_email is required"
        assert admin_password, "admin_password is required"

        with transaction.atomic():
            with schema_context(get_public_schema_name()):
                normalized_domain = cls._normalize_domain(domain_string)
                subdomain = cls._build_subdomain(normalized_domain)
                schema_name = cls._build_unique_schema_name(school_name, subdomain)
                school_code = cls._build_unique_school_code()

                school = School.objects.create(
                    name=school_name.strip(),
                    schema_name=schema_name,
                    subdomain=subdomain,
                    school_code=school_code,
                    contact_email=admin_email.strip().lower(),
                    is_active=True,
                    on_trial=True,
                )

                domain = Domain.objects.create(
                    tenant=school,
                    domain=normalized_domain,
                    is_primary=True,
                )

                principal = CustomUser.objects.create_user(
                    email=admin_email.strip().lower(),
                    password=admin_password,
                    is_active=True,
                    is_staff=True,
                )

                principal_role, _ = Role.objects.get_or_create(
                    name=Role.RoleName.PRINCIPAL,
                    defaults={
                        "description": (
                            "Tenant principal with school-wide administrative access."
                        )
                    },
                )

                role_binding = TenantUserRole.objects.create(
                    user=principal,
                    school=school,
                    role=principal_role,
                    granted_by=principal,
                    is_active=True,
                )

        return ProvisionedTenantContext(
            school=school,
            domain=domain,
            principal=principal,
            role_binding=role_binding,
        )

    @staticmethod
    def _normalize_domain(domain_string: str) -> str:
        parsed = urlparse(
            domain_string
            if "://" in domain_string
            else f"https://{domain_string}"
        )
        normalized_domain = (parsed.netloc or parsed.path).strip().lower()
        assert normalized_domain, "domain_string must contain a resolvable hostname"
        return normalized_domain

    @classmethod
    def _build_subdomain(cls, normalized_domain: str) -> str:
        leftmost_label = normalized_domain.split(".", 1)[0]
        slug = slugify(leftmost_label).replace("-", "-")
        assert slug, "domain_string must contain a valid leftmost label"
        return slug[:63]

    @classmethod
    def _build_unique_schema_name(cls, school_name: str, subdomain: str) -> str:
        base = slugify(school_name).replace("-", "_") or subdomain.replace("-", "_")
        stem = f"sch_{base}"[:54].strip("_") or "sch_darasa"
        while True:
            candidate = f"{stem}_{uuid.uuid4().hex[:8]}".lower()[:63]
            if not School.objects.filter(schema_name=candidate).exists():
                return candidate

    @staticmethod
    def _build_unique_school_code() -> str:
        while True:
            candidate = f"SCH{uuid.uuid4().hex[:9]}".upper()
            if not School.objects.filter(school_code=candidate).exists():
                return candidate
