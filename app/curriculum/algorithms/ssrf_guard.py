"""Fail-closed host validation for curriculum source metadata.

The guard performs string/IP classification only.  It deliberately does not
resolve DNS or make network calls because CCT is a governance record, not a
crawler.  Future fetch code must pass through this allowlist before touching a
network socket.
"""

from __future__ import annotations

import ipaddress

from django.core.exceptions import ValidationError


METADATA_HOSTS = frozenset({"169.254.169.254"})
INTERNAL_HOSTS = frozenset({"localhost", "metadata", "metadata.google.internal"})


def _normalize_host(host: str) -> str:
    return host.strip().lower().rstrip(".")


def validate_host(host: str, *, allowed_domains: list[str] | tuple[str, ...]) -> str:
    normalized_host = _normalize_host(host)
    allowed = {_normalize_host(domain) for domain in allowed_domains if domain.strip()}

    if not normalized_host:
        raise ValidationError({"source_url": "Source host is required."})
    if normalized_host in INTERNAL_HOSTS or normalized_host.endswith(".local"):
        raise ValidationError({"source_url": "Internal hosts are not allowed."})
    if not allowed:
        raise ValidationError({"allowed_domains": "Allowed domains are required."})

    try:
        address = ipaddress.ip_address(normalized_host.strip("[]"))
    except ValueError:
        if normalized_host not in allowed:
            raise ValidationError({"source_url": "Source host is not approved."})
        return normalized_host

    if str(address) in METADATA_HOSTS:
        raise ValidationError({"source_url": "Metadata endpoints are not allowed."})
    if (
        address.is_loopback
        or address.is_private
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    ):
        raise ValidationError(
            {"source_url": "Internal network addresses are not allowed."}
        )
    if normalized_host not in allowed:
        raise ValidationError({"source_url": "Source host is not approved."})
    return normalized_host
