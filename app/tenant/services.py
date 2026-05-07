from __future__ import annotations

import uuid
import re
from dataclasses import dataclass
from urllib.parse import urlparse

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.utils.text import slugify
from django_tenants.utils import get_public_schema_name, schema_context

from core.models import CustomUser, Role, TenantUserRole
from tenant.models import Domain, School

HOSTNAME_LABEL_RE = re.compile(
    r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$"
)


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
        school_name = cls._require_non_blank(school_name, "school_name")
        admin_email = cls._normalize_admin_email(admin_email)
        admin_password = cls._require_secret(admin_password, "admin_password")

        with transaction.atomic():
            with schema_context(get_public_schema_name()):
                normalized_domain = cls._normalize_domain(domain_string)
                if Domain.objects.filter(domain=normalized_domain).exists():
                    raise ValueError("domain_string cannot be provisioned")
                subdomain = cls._build_subdomain(normalized_domain)
                schema_name = cls._build_unique_schema_name(school_name, subdomain)
                school_code = cls._build_unique_school_code()

                school = School.objects.create(
                    name=school_name,
                    schema_name=schema_name,
                    subdomain=subdomain,
                    school_code=school_code,
                    contact_email=admin_email,
                    is_active=True,
                    on_trial=True,
                )

                domain = Domain.objects.create(
                    tenant=school,
                    domain=normalized_domain,
                    is_primary=True,
                )

                principal = CustomUser.objects.create_user(
                    email=admin_email,
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
    def _require_non_blank(value: str, field_name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field_name} is required")
        return value.strip()

    @staticmethod
    def _require_secret(value: str, field_name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field_name} is required")
        return value

    @classmethod
    def _normalize_admin_email(cls, admin_email: str) -> str:
        normalized_email = cls._require_non_blank(admin_email, "admin_email").lower()
        try:
            validate_email(normalized_email)
        except ValidationError as exc:
            raise ValueError("admin_email is invalid") from exc
        return normalized_email

    @staticmethod
    def _normalize_domain(domain_string: str) -> str:
        if not isinstance(domain_string, str) or not domain_string.strip():
            raise ValueError("domain_string is required")

        parsed = urlparse(
            domain_string.strip()
            if "://" in domain_string
            else f"https://{domain_string.strip()}"
        )
        try:
            hostname = (parsed.hostname or "").strip().rstrip(".").lower()
        except ValueError as exc:
            raise ValueError("domain_string is invalid") from exc

        if not hostname:
            raise ValueError("domain_string must contain a resolvable hostname")

        try:
            normalized_domain = hostname.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise ValueError("domain_string is invalid") from exc

        labels = normalized_domain.split(".")
        if (
            len(normalized_domain) > 253
            or any(not label for label in labels)
            or any(not HOSTNAME_LABEL_RE.fullmatch(label) for label in labels)
        ):
            raise ValueError("domain_string is invalid")

        return normalized_domain

    @classmethod
    def _build_subdomain(cls, normalized_domain: str) -> str:
        leftmost_label = normalized_domain.split(".", 1)[0]
        slug = slugify(leftmost_label).replace("-", "-")
        if not slug:
            raise ValueError("domain_string must contain a valid leftmost label")
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
