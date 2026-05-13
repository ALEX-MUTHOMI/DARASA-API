"""Build deterministic idempotency keys for semantic event facts.

At-least-once systems retry.  The same semantic fact must therefore produce the
same key so duplicate writes are rejected by the database rather than becoming
duplicate downstream work.
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError

from events.algorithms.event_type_normalizer import build_event_name


def build_idempotency_key(
    *,
    tenant_id: Any,
    event_type: str,
    event_version: int,
    resource_type: str,
    resource_id: Any,
    semantic_action: str,
) -> str:
    required = {
        "tenant_id": tenant_id,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "semantic_action": semantic_action,
    }
    if any(value in (None, "") for value in required.values()):
        raise ValidationError({"idempotency_key": "Idempotency inputs are required."})
    event_name = build_event_name(event_type, event_version)
    return (
        f"tenant:{tenant_id}:{event_name}:"
        f"{resource_type}:{resource_id}:{semantic_action}"
    )
