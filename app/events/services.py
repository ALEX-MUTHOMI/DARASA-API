"""Write-side services for the transactional event backbone.

Events are facts.  Services validate the contract, producer, tenant, payload,
and idempotency key before a row reaches the outbox.  Dispatch happens later in
bounded batches so domain transactions never depend on a broker being healthy.

Phase 5B keeps security-critical decisions in `events.algorithms`.  This module
fetches contracts, writes rows, and records attempts; it does not invent inline
event safety rules.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
from typing import Any
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction
from django.utils import timezone

from events.algorithms.backoff import calculate_backoff_seconds
from events.algorithms.consumer_idempotency import (
    ensure_consumer_tenant_matches,
    should_skip_consumer,
)
from events.algorithms.dead_letter_classifier import (
    classify_dead_letter_reason,
    sanitize_dead_letter_text,
)
from events.algorithms.dispatch_batch_planner import plan_dispatch_batch
from events.algorithms.event_contract_validator import (
    validate_event_contract as validate_event_contract_algorithm,
)
from events.algorithms.partition_key_builder import build_partition_key
from events.algorithms.producer_authorizer import (
    authorize_consumer,
    authorize_producer,
)
from events.algorithms.retry_policy import RETRYABLE, decide_retry
from events.constants import (
    DEFAULT_RETRY_DELAY_SECONDS,
    INITIAL_EVENT_CONTRACTS,
    LOCK_TIMEOUT_SECONDS,
    MAX_RELAY_BATCH_SIZE,
    MAX_RETRY_ATTEMPTS,
    MAX_EVENT_PAYLOAD_BYTES,
)
from events.handlers import get_handlers
from events.models import (
    AuditEvent,
    DeadLetterEvent,
    EventConsumerState,
    EventDispatchAttempt,
    EventOutbox,
    EventTypeRegistry,
)
from events.validators import (
    reject_sensitive_payload,
    validate_event_type_name,
    validate_partition_key,
    validate_priority,
)


class RetryableEventError(Exception):
    """Handler failure that can be retried within the bounded retry policy."""


class PermanentEventError(Exception):
    """Handler failure that should move the event to dead letter immediately."""


def _sanitize_error(message: str) -> str:
    return sanitize_dead_letter_text(str(message or "")[:255])


def _registry_contract(registry: EventTypeRegistry) -> dict[str, Any]:
    return {
        "event_type": registry.event_type,
        "event_version": registry.event_version,
        "allowed_producers": registry.allowed_producers,
        "requires_tenant": registry.requires_tenant,
        "payload_schema": registry.payload_schema,
        "is_active": registry.is_active,
    }


def register_event_type(
    *,
    event_type: str,
    event_version: int,
    description: str,
    source_module: str,
    allowed_producers: list[str],
    allowed_consumers: list[str],
    requires_tenant: bool,
    payload_schema: dict[str, Any],
    priority: str = "normal",
    pii_policy: str = EventTypeRegistry.PiiPolicy.REFERENCES_ONLY,
    retention_days: int = 365,
    is_active: bool = True,
) -> EventTypeRegistry:
    return EventTypeRegistry.objects.create(
        event_type=event_type,
        event_version=event_version,
        description=description,
        source_module=source_module,
        allowed_producers=allowed_producers,
        allowed_consumers=allowed_consumers,
        requires_tenant=requires_tenant,
        payload_schema=payload_schema,
        priority=priority,
        pii_policy=pii_policy,
        retention_days=retention_days,
        is_active=is_active,
    )


def register_initial_event_types() -> None:
    for contract in INITIAL_EVENT_CONTRACTS:
        EventTypeRegistry.objects.get_or_create(
            event_type=contract["event_type"],
            event_version=contract["event_version"],
            defaults={
                "description": contract["description"],
                "source_module": contract["source_module"],
                "allowed_producers": contract["allowed_producers"],
                "allowed_consumers": contract["allowed_consumers"],
                "requires_tenant": contract["requires_tenant"],
                "payload_schema": contract["payload_schema"],
                "priority": contract["priority"],
            },
        )


def validate_event_contract(
    *,
    event_type: str,
    event_version: int,
) -> EventTypeRegistry:
    return EventTypeRegistry.objects.get(
        event_type=validate_event_type_name(event_type),
        event_version=event_version,
        is_active=True,
    )


def validate_event_producer(*, registry: EventTypeRegistry, producer: str) -> None:
    authorize_producer(producer=producer, allowed_producers=registry.allowed_producers)


def validate_event_payload_for_registry(
    *,
    registry: EventTypeRegistry,
    payload: Mapping[str, Any],
) -> None:
    validate_event_contract_algorithm(
        contract=_registry_contract(registry),
        event_type=registry.event_type,
        event_version=registry.event_version,
        producer=registry.source_module,
        tenant_id="not-required" if not registry.requires_tenant else "tenant",
        payload=payload,
        priority=registry.priority,
        max_payload_bytes=MAX_EVENT_PAYLOAD_BYTES,
    )


reject_sensitive_payload = reject_sensitive_payload


@transaction.atomic
def write_outbox_event(
    *,
    event_type: str,
    event_version: int,
    source_module: str,
    idempotency_key: str,
    payload: Mapping[str, Any],
    tenant: Any | None = None,
    actor_id: Any | None = None,
    correlation_id: Any | None = None,
    causation_id: Any | None = None,
    partition_key: str | None = None,
    occurred_at: Any | None = None,
    priority: str | None = None,
) -> EventOutbox:
    registry = validate_event_contract(
        event_type=event_type,
        event_version=event_version,
    )
    validate_event_producer(registry=registry, producer=source_module)
    event_priority = validate_priority(priority or registry.priority)
    tenant_id = tenant.id if tenant is not None else None
    validate_event_contract_algorithm(
        contract=_registry_contract(registry),
        event_type=registry.event_type,
        event_version=registry.event_version,
        producer=source_module,
        tenant_id=tenant_id,
        payload=payload,
        priority=event_priority,
        max_payload_bytes=MAX_EVENT_PAYLOAD_BYTES,
    )
    partition = partition_key or build_partition_key(
        tenant_id=tenant_id,
        event_type=registry.event_type,
        requires_tenant=registry.requires_tenant,
    )
    return EventOutbox.objects.create(
        event_type=registry.event_type,
        event_version=registry.event_version,
        tenant=tenant,
        actor_id=actor_id,
        correlation_id=correlation_id or uuid4(),
        causation_id=causation_id,
        idempotency_key=idempotency_key,
        source_module=source_module,
        partition_key=validate_partition_key(partition),
        priority=event_priority,
        payload=dict(payload),
        occurred_at=occurred_at or timezone.now(),
    )


record_event = write_outbox_event


def record_audit_event(
    *,
    action: str,
    resource_type: str,
    resource_id: str,
    tenant: Any | None = None,
    actor_id: Any | None = None,
    event_outbox: EventOutbox | None = None,
    old_state_hash: str = "",
    new_state_hash: str = "",
    correlation_id: Any | None = None,
    causation_id: Any | None = None,
    ip_address: str | None = None,
    user_agent: str = "",
) -> AuditEvent:
    return AuditEvent.objects.create(
        tenant=tenant,
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        event_outbox=event_outbox,
        old_state_hash=old_state_hash,
        new_state_hash=new_state_hash,
        correlation_id=correlation_id or uuid4(),
        causation_id=causation_id,
        ip_address=ip_address,
        user_agent=user_agent,
    )


def lock_pending_events(
    *,
    dispatcher_name: str,
    batch_size: int = MAX_RELAY_BATCH_SIZE,
) -> list[EventOutbox]:
    now = timezone.now()
    safe_batch_size = max(1, min(batch_size, MAX_RELAY_BATCH_SIZE))
    candidates = list(
        EventOutbox.objects.filter(
            status__in=[
                EventOutbox.Status.PENDING,
                EventOutbox.Status.FAILED_RETRYABLE,
                EventOutbox.Status.LOCKED,
            ],
            available_at__lte=now,
        )
        .filter(
            models.Q(
                status__in=[
                    EventOutbox.Status.PENDING,
                    EventOutbox.Status.FAILED_RETRYABLE,
                ]
            )
            | models.Q(status=EventOutbox.Status.LOCKED)
        )
        .order_by("available_at", "occurred_at")[: safe_batch_size * 3]
    )
    selected = plan_dispatch_batch(
        events=candidates,
        max_batch_size=safe_batch_size,
        now=now,
        lock_timeout_seconds=LOCK_TIMEOUT_SECONDS,
    )
    ids = [event.id for event in selected]
    EventOutbox.objects.filter(id__in=ids).update(
        status=EventOutbox.Status.LOCKED,
        locked_at=now,
        locked_by=dispatcher_name,
    )
    return list(EventOutbox.objects.filter(id__in=ids).order_by("occurred_at"))


def _attempt_number(event: EventOutbox) -> int:
    return event.dispatch_attempts.count() + 1


def mark_event_dispatched(
    *,
    event: EventOutbox,
    attempt: EventDispatchAttempt | None = None,
) -> EventOutbox:
    event.status = EventOutbox.Status.DISPATCHED
    event.dispatched_at = timezone.now()
    event.save(update_fields=["status", "dispatched_at", "updated_at"])
    if attempt is not None:
        attempt.status = EventDispatchAttempt.Status.SUCCEEDED
        attempt.finished_at = timezone.now()
        attempt.save(update_fields=["status", "finished_at"])
    return event


def mark_event_failed_retryable(
    *,
    event: EventOutbox,
    attempt: EventDispatchAttempt,
    error_message: str,
) -> EventOutbox:
    attempt.status = EventDispatchAttempt.Status.FAILED_RETRYABLE
    attempt.error_message = _sanitize_error(error_message)
    attempt.finished_at = timezone.now()
    attempt.save(update_fields=["status", "error_message", "finished_at"])
    failure_class = RETRYABLE
    decision = decide_retry(
        failure_class=failure_class,
        attempt_number=attempt.attempt_number,
        max_attempts=MAX_RETRY_ATTEMPTS,
    )
    if decision.should_dead_letter:
        return move_event_to_dead_letter(
            event=event,
            reason=classify_dead_letter_reason(
                failure_class=failure_class,
                attempt_number=attempt.attempt_number,
                max_attempts=MAX_RETRY_ATTEMPTS,
            ),
            error_message=error_message,
            failed_after_attempts=attempt.attempt_number,
        ).event_outbox
    event.status = EventOutbox.Status.FAILED_RETRYABLE
    event.available_at = timezone.now() + timedelta(
        seconds=calculate_backoff_seconds(
            attempt_number=attempt.attempt_number,
            base_delay_seconds=DEFAULT_RETRY_DELAY_SECONDS,
            max_delay_seconds=DEFAULT_RETRY_DELAY_SECONDS * 8,
        )
    )
    event.save(update_fields=["status", "available_at", "updated_at"])
    return event


def move_event_to_dead_letter(
    *,
    event: EventOutbox,
    reason: str,
    error_message: str,
    failed_after_attempts: int,
) -> DeadLetterEvent:
    event.status = EventOutbox.Status.DEAD_LETTERED
    event.save(update_fields=["status", "updated_at"])
    return DeadLetterEvent.objects.create(
        event_outbox=event,
        event_type=event.event_type,
        event_version=event.event_version,
        tenant=event.tenant,
        reason=_sanitize_error(reason),
        sanitized_error=_sanitize_error(error_message),
        failed_after_attempts=failed_after_attempts,
    )


def already_processed(*, event_id: Any, consumer_name: str) -> bool:
    state = EventConsumerState.objects.filter(
        event_id=event_id,
        consumer_name=consumer_name,
    ).first()
    return should_skip_consumer(status=state.status if state else None)


def record_consumer_started(
    *,
    event: EventOutbox,
    consumer_name: str,
    tenant: Any | None = None,
) -> EventConsumerState:
    ensure_consumer_tenant_matches(
        event_tenant_id=event.tenant_id,
        consumer_tenant_id=(tenant.id if tenant is not None else None),
    )
    state, _ = EventConsumerState.objects.get_or_create(
        event_id=event.id,
        consumer_name=consumer_name,
        defaults={
            "event_outbox": event,
            "tenant": tenant or event.tenant,
            "status": EventConsumerState.Status.STARTED,
        },
    )
    return state


def record_consumer_processed(
    *,
    event: EventOutbox,
    consumer_name: str,
) -> EventConsumerState:
    state = record_consumer_started(event=event, consumer_name=consumer_name)
    state.status = EventConsumerState.Status.PROCESSED
    state.processed_at = timezone.now()
    state.save(update_fields=["status", "processed_at", "updated_at"])
    return state


def record_consumer_failed(
    *,
    event: EventOutbox,
    consumer_name: str,
    failure_reason: str,
) -> EventConsumerState:
    state = record_consumer_started(event=event, consumer_name=consumer_name)
    state.status = EventConsumerState.Status.FAILED
    state.failure_reason = _sanitize_error(failure_reason)
    state.save(update_fields=["status", "failure_reason", "updated_at"])
    return state


def dispatch_pending_events(
    *,
    dispatcher_name: str = "local-relay",
    batch_size: int = MAX_RELAY_BATCH_SIZE,
) -> int:
    dispatched = 0
    for event in lock_pending_events(
        dispatcher_name=dispatcher_name,
        batch_size=batch_size,
    ):
        active_consumer = ""
        attempt = EventDispatchAttempt.objects.create(
            event_outbox=event,
            attempt_number=_attempt_number(event),
            dispatcher_name=dispatcher_name,
            status=EventDispatchAttempt.Status.STARTED,
        )
        try:
            handlers = get_handlers(event.event_type)
            if not handlers:
                mark_event_dispatched(event=event, attempt=attempt)
                dispatched += 1
                continue
            for consumer_name, handler in handlers:
                active_consumer = consumer_name
                registry = validate_event_contract(
                    event_type=event.event_type,
                    event_version=event.event_version,
                )
                authorize_consumer(
                    consumer=consumer_name,
                    allowed_consumers=registry.allowed_consumers,
                )
                if already_processed(event_id=event.id, consumer_name=consumer_name):
                    continue
                record_consumer_started(event=event, consumer_name=consumer_name)
                handler(event)
                record_consumer_processed(event=event, consumer_name=consumer_name)
            mark_event_dispatched(event=event, attempt=attempt)
            dispatched += 1
        except RetryableEventError as exc:
            if active_consumer:
                record_consumer_failed(
                    event=event,
                    consumer_name=active_consumer,
                    failure_reason=str(exc),
                )
            mark_event_failed_retryable(
                event=event,
                attempt=attempt,
                error_message=str(exc),
            )
        except (PermanentEventError, ValidationError, IntegrityError) as exc:
            if active_consumer:
                record_consumer_failed(
                    event=event,
                    consumer_name=active_consumer,
                    failure_reason=str(exc),
                )
            move_event_to_dead_letter(
                event=event,
                reason="permanent_failure",
                error_message=str(exc),
                failed_after_attempts=attempt.attempt_number,
            )
            attempt.status = EventDispatchAttempt.Status.DEAD_LETTERED
            attempt.finished_at = timezone.now()
            attempt.save(update_fields=["status", "finished_at"])
    return dispatched
