"""Classify and sanitize dead-letter reasons.

Dead-letter rows are operational evidence, not a place to copy raw payloads or
exception dumps.  This module produces stable, sanitized reasons that keep
poison events auditable without leaking sensitive values.
"""

from __future__ import annotations

from events.algorithms.payload_safety_guard import sanitize_failure_text
from events.algorithms.retry_policy import (
    INVALID_PAYLOAD,
    PERMANENT,
    SCHEMA_MISMATCH,
    TENANT_MISMATCH,
    UNAUTHORIZED_PRODUCER,
)


REASON_BY_FAILURE = {
    INVALID_PAYLOAD: "invalid_payload",
    PERMANENT: "handler_permanent_failure",
    SCHEMA_MISMATCH: "schema_mismatch",
    TENANT_MISMATCH: "tenant_mismatch",
    UNAUTHORIZED_PRODUCER: "unauthorized_producer",
}


def classify_dead_letter_reason(
    *,
    failure_class: str,
    attempt_number: int,
    max_attempts: int,
) -> str:
    if attempt_number >= max_attempts:
        return "max_retries_exceeded"
    return REASON_BY_FAILURE.get(failure_class, "handler_permanent_failure")


def sanitize_dead_letter_text(value: str) -> str:
    return sanitize_failure_text(value, fallback="sanitized_dead_letter")
