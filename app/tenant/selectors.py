from __future__ import annotations

from tenant.models import Domain, School


def get_school_by_domain(domain: str) -> School | None:
    if not isinstance(domain, str) or not domain.strip():
        return None
    normalized_domain = domain.strip().lower().rstrip(".")
    return (
        School.objects.filter(
            domains__domain=normalized_domain,
            is_active=True,
        )
        .distinct()
        .first()
    )


def get_school_by_schema(schema_name: str) -> School | None:
    if not isinstance(schema_name, str) or not schema_name.strip():
        return None
    return School.objects.filter(
        schema_name=schema_name.strip().lower(),
        is_active=True,
    ).first()


def get_school_by_subdomain(subdomain: str) -> School | None:
    if not isinstance(subdomain, str) or not subdomain.strip():
        return None
    return School.objects.filter(
        subdomain=subdomain.strip().lower(),
        is_active=True,
    ).first()


def get_primary_domain_for_school(school: School) -> Domain | None:
    if school is None:
        return None
    return Domain.objects.filter(tenant=school, is_primary=True).first()
