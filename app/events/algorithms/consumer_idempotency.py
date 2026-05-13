"""Side-effect-free consumer idempotency decisions.

Delivery is at least once.  Consumers must skip completed or in-flight work and
must fail closed on tenant mismatch before handler code can touch school data.
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError


SKIP_STATUSES = frozenset({"started", "processed"})


def should_skip_consumer(*, status: str | None) -> bool:
    return str(status or "").strip().lower() in SKIP_STATUSES


def ensure_consumer_tenant_matches(
    *,
    event_tenant_id: Any | None,
    consumer_tenant_id: Any | None,
) -> None:
    if event_tenant_id and consumer_tenant_id and event_tenant_id != consumer_tenant_id:
        raise ValidationError({"tenant": "Consumer tenant mismatch."})
