"""Validation for typed, tenant-aware event envelopes.

Validators are intentionally independent of dispatch.  Business services should
fail before writing an outbox row if an event is unknown, spoofed by the wrong
producer, missing tenant context, oversized, or carrying obvious sensitive data.
The implementation delegates to `events.algorithms` so model validation and
service validation share the same deterministic rules.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from django.core.exceptions import ValidationError

from events.algorithms.event_type_normalizer import validate_event_namespace
from events.algorithms.partition_key_builder import (
    validate_partition_key as validate_partition_key_algorithm,
)
from events.algorithms.payload_safety_guard import (
    payload_size_bytes as payload_size_bytes_algorithm,
)
from events.algorithms.payload_safety_guard import (
    reject_sensitive_payload as reject_sensitive_payload_algorithm,
)
from events.algorithms.payload_safety_guard import (
    validate_payload_size as validate_payload_size_algorithm,
)
from events.algorithms.payload_schema_validator import (
    validate_payload_schema as validate_payload_schema_algorithm,
)
from events.algorithms.priority_ordering import (
    validate_priority as validate_priority_algorithm,
)
from events.constants import EVENT_PRIORITIES, MAX_EVENT_PAYLOAD_BYTES


def validate_event_type_name(event_type: str) -> str:
    return validate_event_namespace(event_type)


def validate_priority(priority: str) -> str:
    value = validate_priority_algorithm(priority)
    if value not in EVENT_PRIORITIES:
        raise ValidationError({"priority": "Event priority is invalid."})
    return value


def validate_partition_key(partition_key: str) -> str:
    return validate_partition_key_algorithm(partition_key)


def payload_size_bytes(payload: Mapping[str, Any]) -> int:
    return payload_size_bytes_algorithm(payload)


def validate_payload_size(payload: Mapping[str, Any]) -> None:
    validate_payload_size_algorithm(payload, max_bytes=MAX_EVENT_PAYLOAD_BYTES)


def reject_sensitive_payload(payload: Mapping[str, Any]) -> None:
    reject_sensitive_payload_algorithm(payload)


def validate_payload_schema(
    *,
    payload: Mapping[str, Any],
    payload_schema: Mapping[str, Any],
) -> None:
    validate_payload_schema_algorithm(payload=payload, payload_schema=payload_schema)


def validate_event_payload(
    *,
    payload: Mapping[str, Any],
    payload_schema: Mapping[str, Any],
) -> None:
    if not isinstance(payload, Mapping):
        raise ValidationError({"payload": "Event payload must be an object."})
    validate_payload_schema(payload=payload, payload_schema=payload_schema)
    validate_payload_size(payload)
    reject_sensitive_payload(payload)
