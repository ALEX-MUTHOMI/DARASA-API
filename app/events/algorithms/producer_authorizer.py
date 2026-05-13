"""Authorize event producers using exact allowlist matching.

Producer checks belong in the algorithm layer because event spoofing is a
cross-cutting risk.  Arbitrary modules must not be able to emit trusted facts
by guessing an event type.
"""

from __future__ import annotations

from collections.abc import Iterable

from django.core.exceptions import ValidationError


def authorize_producer(*, producer: str, allowed_producers: Iterable[str]) -> str:
    value = str(producer or "").strip()
    allowed = {str(item).strip() for item in allowed_producers if str(item).strip()}
    if not value or value not in allowed:
        raise ValidationError({"source_module": "Producer is not allowlisted."})
    return value


def authorize_consumer(*, consumer: str, allowed_consumers: Iterable[str]) -> str:
    value = str(consumer or "").strip()
    allowed = {str(item).strip() for item in allowed_consumers if str(item).strip()}
    if not value or value not in allowed:
        raise ValidationError({"consumer": "Consumer is not allowlisted."})
    return value
