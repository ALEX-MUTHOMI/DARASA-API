"""Validate and order event priorities for bounded dispatch.

The local relay must process urgent security and school-facing facts before
background work while keeping FIFO order inside each priority.  The same order
can later map to broker priority or queue selection.
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError


PRIORITY_ORDER = {
    "critical": 0,
    "high": 1,
    "normal": 2,
    "low": 3,
    "background": 4,
}
EVENT_PRIORITIES = frozenset(PRIORITY_ORDER)


def validate_priority(priority: str) -> str:
    value = str(priority or "").strip().lower()
    if value not in EVENT_PRIORITIES:
        raise ValidationError({"priority": "Event priority is invalid."})
    return value


def priority_rank(priority: str) -> int:
    return PRIORITY_ORDER[validate_priority(priority)]


def sort_events_for_dispatch(events: list[Any]) -> list[Any]:
    return sorted(
        events,
        key=lambda event: (
            priority_rank(getattr(event, "priority", "normal")),
            getattr(event, "occurred_at", None),
        ),
    )
