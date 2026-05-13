"""Validate an event emission against its registered contract.

This module keeps contract checks independent of ORM writes: callers provide a
contract mapping, producer, tenant context, payload, and priority.  The service
layer is then only responsible for fetching the contract and writing the row.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from django.core.exceptions import ValidationError

from events.algorithms.event_type_normalizer import validate_event_namespace
from events.algorithms.payload_schema_validator import validate_payload_schema
from events.algorithms.payload_safety_guard import (
    reject_sensitive_payload,
    validate_payload_size,
)
from events.algorithms.priority_ordering import validate_priority
from events.algorithms.producer_authorizer import authorize_producer


def validate_event_contract(
    *,
    contract: Mapping[str, Any],
    event_type: str,
    event_version: int,
    producer: str,
    tenant_id: Any | None,
    payload: Mapping[str, Any],
    priority: str,
    max_payload_bytes: int,
) -> None:
    if not contract or not contract.get("is_active", True):
        raise ValidationError({"event_type": "Active event type is required."})
    if validate_event_namespace(event_type) != contract.get("event_type"):
        raise ValidationError({"event_type": "Event type does not match contract."})
    if int(event_version) != int(contract.get("event_version", 0)):
        raise ValidationError({"event_version": "Event version is invalid."})
    authorize_producer(
        producer=producer,
        allowed_producers=contract.get("allowed_producers", []),
    )
    if contract.get("requires_tenant") and tenant_id is None:
        raise ValidationError({"tenant": "Tenant is required for this event."})
    validate_priority(priority)
    validate_payload_schema(
        payload=payload,
        payload_schema=contract.get("payload_schema", {}),
    )
    validate_payload_size(payload, max_bytes=max_payload_bytes)
    reject_sensitive_payload(payload)
