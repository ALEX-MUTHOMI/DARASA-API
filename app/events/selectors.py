"""Read-only event and audit selectors."""

from __future__ import annotations

from django.db.models import Count, QuerySet
from django.utils import timezone

from events.models import (
    AuditEvent,
    DeadLetterEvent,
    EventConsumerState,
    EventDispatchAttempt,
    EventOutbox,
)
from tenant.models import School


def get_pending_outbox_events() -> QuerySet[EventOutbox]:
    return EventOutbox.objects.filter(
        status__in=[
            EventOutbox.Status.PENDING,
            EventOutbox.Status.FAILED_RETRYABLE,
        ],
        available_at__lte=timezone.now(),
    ).order_by("priority", "occurred_at")


def get_dead_letter_events() -> QuerySet[DeadLetterEvent]:
    return DeadLetterEvent.objects.select_related("event_outbox", "tenant").order_by(
        "-moved_at"
    )


def get_dispatch_attempts_for_event(
    event: EventOutbox,
) -> QuerySet[EventDispatchAttempt]:
    return event.dispatch_attempts.order_by("attempt_number")


def get_consumer_states_for_event(event: EventOutbox) -> QuerySet[EventConsumerState]:
    return event.consumer_states.order_by("consumer_name")


def get_audit_events_for_tenant(*, tenant: School) -> QuerySet[AuditEvent]:
    return AuditEvent.objects.filter(tenant=tenant).order_by("-occurred_at")


def get_audit_events_for_resource(
    *,
    resource_type: str,
    resource_id: str,
    tenant: School | None = None,
) -> QuerySet[AuditEvent]:
    queryset = AuditEvent.objects.filter(
        resource_type=resource_type,
        resource_id=resource_id,
    )
    if tenant is not None:
        queryset = queryset.filter(tenant=tenant)
    return queryset.order_by("-occurred_at")


def get_event_backlog_summary() -> dict[str, int]:
    rows = EventOutbox.objects.values("status").annotate(count=Count("id"))
    return {row["status"]: row["count"] for row in rows}


def get_oldest_pending_event_age() -> float | None:
    event = get_pending_outbox_events().order_by("occurred_at").first()
    if event is None:
        return None
    return (timezone.now() - event.occurred_at).total_seconds()


def get_retry_summary() -> dict[str, int]:
    return {
        "retryable": EventOutbox.objects.filter(
            status=EventOutbox.Status.FAILED_RETRYABLE
        ).count()
    }


def get_dead_letter_summary() -> dict[str, int]:
    rows = DeadLetterEvent.objects.values("event_type").annotate(count=Count("id"))
    return {row["event_type"]: row["count"] for row in rows}
