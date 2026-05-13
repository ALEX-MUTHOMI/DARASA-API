from __future__ import annotations

from django.core.exceptions import ValidationError


APPROVED_AUTHORITY_DOMAINS = {
    "kicd": frozenset({"kicd.ac.ke", "www.kicd.ac.ke"}),
    "knec": frozenset({"knec.ac.ke", "www.knec.ac.ke"}),
    "moe": frozenset({"education.go.ke", "www.education.go.ke"}),
    "ministry-of-education": frozenset({"education.go.ke", "www.education.go.ke"}),
    "tsc": frozenset({"tsc.go.ke", "www.tsc.go.ke"}),
}


def validate_authority_domains(
    *,
    authority_code: str,
    allowed_domains: list[str],
) -> list[str]:
    approved = APPROVED_AUTHORITY_DOMAINS.get(authority_code)
    if not approved:
        raise ValidationError({"code": "Curriculum authority is not allowlisted."})

    normalized = [
        domain.strip().lower().rstrip(".")
        for domain in allowed_domains
        if isinstance(domain, str) and domain.strip()
    ]
    if not normalized:
        raise ValidationError({"allowed_domains": "Allowed domains are required."})
    if any(domain not in approved for domain in normalized):
        raise ValidationError(
            {"allowed_domains": "Authority domain is not allowlisted."}
        )
    return normalized
