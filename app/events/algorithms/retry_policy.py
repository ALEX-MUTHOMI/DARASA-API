"""Classify event failures and decide whether another retry is safe.

The relay must not retry forever.  These helpers separate retryable transient
failures from permanent contract or authorization failures so poison events move
to dead letter instead of burning workers indefinitely.
"""

from __future__ import annotations

from dataclasses import dataclass


RETRYABLE = "retryable"
PERMANENT = "permanent"
INVALID_PAYLOAD = "invalid_payload"
UNAUTHORIZED_PRODUCER = "unauthorized_producer"
TENANT_MISMATCH = "tenant_mismatch"
SCHEMA_MISMATCH = "schema_mismatch"
CONSUMER_BUG = "consumer_bug"
EXTERNAL_DEPENDENCY_UNAVAILABLE = "external_dependency_unavailable"


@dataclass(frozen=True)
class RetryDecision:
    failure_class: str
    should_retry: bool
    should_dead_letter: bool


def classify_failure(error: Exception | str) -> str:
    name = error.__class__.__name__ if isinstance(error, Exception) else str(error)
    lowered = name.lower()
    if "retryable" in lowered or "temporary" in lowered or "unavailable" in lowered:
        return RETRYABLE
    if "validation" in lowered or "payload" in lowered:
        return INVALID_PAYLOAD
    if "tenant" in lowered:
        return TENANT_MISMATCH
    if "producer" in lowered or "consumer" in lowered or "allowlist" in lowered:
        return UNAUTHORIZED_PRODUCER
    return PERMANENT


def decide_retry(
    *,
    failure_class: str,
    attempt_number: int,
    max_attempts: int,
) -> RetryDecision:
    if failure_class == RETRYABLE and attempt_number < max_attempts:
        return RetryDecision(failure_class, True, False)
    return RetryDecision(failure_class, False, True)
