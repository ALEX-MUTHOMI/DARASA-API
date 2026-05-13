"""Plan bounded dispatch batches without mutating event rows.

Relay workers should take predictable slices of work, skip fresh locks, reclaim
expired locks only when allowed by the caller, and order by priority then age.
The database layer performs the actual row locking after this plan is built.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.core.exceptions import ValidationError

from events.algorithms.priority_ordering import sort_events_for_dispatch


READY_STATUSES = frozenset({"pending", "failed_retryable"})
LOCKED_STATUS = "locked"


def plan_dispatch_batch(
    *,
    events: list[Any],
    max_batch_size: int,
    now: Any,
    lock_timeout_seconds: int,
) -> list[Any]:
    if max_batch_size < 1:
        raise ValidationError({"batch_size": "Batch size must be positive."})
    cutoff = now - timedelta(seconds=lock_timeout_seconds)
    ready = []
    for event in events:
        status = getattr(event, "status", "")
        available_at = getattr(event, "available_at", None)
        locked_at = getattr(event, "locked_at", None)
        if available_at and available_at > now:
            continue
        if status in READY_STATUSES:
            ready.append(event)
        elif status == LOCKED_STATUS and locked_at and locked_at < cutoff:
            ready.append(event)
    return sort_events_for_dispatch(ready)[:max_batch_size]
