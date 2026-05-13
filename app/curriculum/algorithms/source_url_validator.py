"""Validate official curriculum source URLs without opening the network.

CCT treats URLs as evidence metadata, not fetch instructions.  The validator
therefore accepts only canonical HTTPS references on pre-approved authority
domains and rejects URL tricks before any future ingestion layer could see
them.
"""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from django.core.exceptions import ValidationError

from curriculum.algorithms.ssrf_guard import validate_host


ALLOWED_SCHEMES = frozenset({"https"})


def validate_source_url(
    source_url: str,
    *,
    allowed_domains: list[str] | tuple[str, ...],
) -> str:
    value = source_url.strip()
    if not value:
        raise ValidationError({"source_url": "Source URL is required."})

    parsed = urlsplit(value)
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise ValidationError({"source_url": "HTTPS source URLs are required."})
    if not parsed.hostname:
        raise ValidationError({"source_url": "Malformed source URL."})
    if parsed.username or parsed.password:
        raise ValidationError(
            {"source_url": "Credentialed source URLs are not allowed."}
        )

    host = validate_host(parsed.hostname, allowed_domains=allowed_domains)
    netloc = host
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValidationError({"source_url": "Invalid source URL port."}) from exc
    if port and port != 443:
        raise ValidationError(
            {"source_url": "Only the canonical HTTPS port is allowed."}
        )
    if port:
        netloc = f"{host}:{port}"

    return urlunsplit(
        (
            parsed.scheme.lower(),
            netloc,
            parsed.path or "/",
            parsed.query,
            "",
        )
    )
