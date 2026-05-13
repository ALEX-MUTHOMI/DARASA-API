"""Persistent event backbone models.

Events are immutable facts written to a transactional outbox.  Producers write
rows in the same database transaction as the business change; a relay dispatches
later so a broker outage cannot corrupt domain state.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from events.validators import (
    reject_sensitive_payload,
    validate_event_payload,
    validate_event_type_name,
    validate_partition_key,
    validate_priority,
)
from tenant.models import School, TimeStampedModel


class EventTypeRegistry(TimeStampedModel):
    class PiiPolicy(models.TextChoices):
        NO_PII = "no_pii", "No PII"
        REFERENCES_ONLY = "references_only", "References only"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_type = models.CharField(max_length=128)
    event_version = models.PositiveIntegerField(default=1)
    description = models.TextField()
    source_module = models.CharField(max_length=64)
    allowed_producers = models.JSONField(default=list)
    allowed_consumers = models.JSONField(default=list)
    requires_tenant = models.BooleanField(default=True)
    pii_policy = models.CharField(
        max_length=32,
        choices=PiiPolicy.choices,
        default=PiiPolicy.REFERENCES_ONLY,
    )
    payload_schema = models.JSONField(default=dict)
    priority = models.CharField(max_length=16, default="normal")
    retention_days = models.PositiveIntegerField(default=365)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta(TimeStampedModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["event_type", "event_version"],
                name="events_type_version_unique",
            ),
        ]
        indexes = [
            models.Index(
                fields=["event_type", "event_version"],
                name="events_type_idx",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        self.event_type = validate_event_type_name(self.event_type)
        self.priority = validate_priority(self.priority)
        if not self.description.strip():
            raise ValidationError({"description": "Description is required."})
        if not self.source_module.strip():
            raise ValidationError({"source_module": "Source module is required."})
        if not isinstance(self.allowed_producers, list) or not self.allowed_producers:
            raise ValidationError({"allowed_producers": "Allowed producers required."})
        if not isinstance(self.allowed_consumers, list):
            raise ValidationError({"allowed_consumers": "Allowed consumers invalid."})
        if not isinstance(self.payload_schema, dict):
            raise ValidationError({"payload_schema": "Payload schema must be object."})

    def save(self, *args: Any, **kwargs: Any) -> Any:
        self.full_clean()
        return super().save(*args, **kwargs)


class EventOutbox(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        LOCKED = "locked", "Locked"
        DISPATCHED = "dispatched", "Dispatched"
        FAILED_RETRYABLE = "failed_retryable", "Failed retryable"
        DEAD_LETTERED = "dead_lettered", "Dead lettered"
        DISCARDED_INVALID = "discarded_invalid", "Discarded invalid"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_type = models.CharField(max_length=128)
    event_version = models.PositiveIntegerField(default=1)
    tenant = models.ForeignKey(
        School,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="event_outbox_records",
    )
    actor_id = models.UUIDField(null=True, blank=True)
    correlation_id = models.UUIDField(default=uuid.uuid4, db_index=True)
    causation_id = models.UUIDField(null=True, blank=True)
    idempotency_key = models.CharField(max_length=160, unique=True)
    source_module = models.CharField(max_length=64)
    partition_key = models.CharField(max_length=128)
    priority = models.CharField(max_length=16, default="normal", db_index=True)
    payload = models.JSONField(default=dict)
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    available_at = models.DateTimeField(default=timezone.now, db_index=True)
    occurred_at = models.DateTimeField(default=timezone.now)
    locked_at = models.DateTimeField(null=True, blank=True)
    locked_by = models.CharField(max_length=128, blank=True)
    dispatched_at = models.DateTimeField(null=True, blank=True)

    class Meta(TimeStampedModel.Meta):
        indexes = [
            models.Index(
                fields=["status", "available_at", "priority", "occurred_at"],
                name="events_outbox_pending_idx",
            ),
            models.Index(fields=["tenant", "status"], name="events_outbox_tenant_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        registry = EventTypeRegistry.objects.filter(
            event_type=self.event_type,
            event_version=self.event_version,
            is_active=True,
        ).first()
        if registry is None:
            raise ValidationError({"event_type": "Active event type is required."})
        if self.source_module not in registry.allowed_producers:
            raise ValidationError({"source_module": "Producer is not allowlisted."})
        if registry.requires_tenant and self.tenant_id is None:
            raise ValidationError({"tenant": "Tenant is required for this event."})
        if not self.idempotency_key.strip():
            raise ValidationError({"idempotency_key": "Idempotency key is required."})
        self.event_type = validate_event_type_name(self.event_type)
        self.priority = validate_priority(self.priority)
        self.partition_key = validate_partition_key(self.partition_key)
        validate_event_payload(
            payload=self.payload,
            payload_schema=registry.payload_schema,
        )

    def save(self, *args: Any, **kwargs: Any) -> Any:
        self.full_clean()
        return super().save(*args, **kwargs)


class EventDispatchAttempt(models.Model):
    class Status(models.TextChoices):
        STARTED = "started", "Started"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED_RETRYABLE = "failed_retryable", "Failed retryable"
        DEAD_LETTERED = "dead_lettered", "Dead lettered"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_outbox = models.ForeignKey(
        EventOutbox,
        on_delete=models.CASCADE,
        related_name="dispatch_attempts",
    )
    attempt_number = models.PositiveIntegerField()
    dispatcher_name = models.CharField(max_length=128)
    status = models.CharField(max_length=32, choices=Status.choices)
    error_code = models.CharField(max_length=64, blank=True)
    error_message = models.CharField(max_length=255, blank=True)
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["event_outbox", "attempt_number"],
                name="events_attempt_idx",
            ),
        ]


class EventConsumerState(TimeStampedModel):
    class Status(models.TextChoices):
        STARTED = "started", "Started"
        PROCESSED = "processed", "Processed"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_outbox = models.ForeignKey(
        EventOutbox,
        on_delete=models.CASCADE,
        related_name="consumer_states",
    )
    event_id = models.UUIDField(db_index=True)
    consumer_name = models.CharField(max_length=128)
    tenant = models.ForeignKey(
        School,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="event_consumer_states",
    )
    status = models.CharField(max_length=32, choices=Status.choices)
    processed_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.CharField(max_length=255, blank=True)

    class Meta(TimeStampedModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["event_id", "consumer_name"],
                name="events_consumer_once_unique",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        if (
            self.tenant_id
            and self.event_outbox_id
            and self.event_outbox.tenant_id
            and self.tenant_id != self.event_outbox.tenant_id
        ):
            raise ValidationError({"tenant": "Consumer tenant mismatch."})
        if self.failure_reason:
            reject_sensitive_payload({"failure_reason": self.failure_reason})

    def save(self, *args: Any, **kwargs: Any) -> Any:
        self.full_clean()
        return super().save(*args, **kwargs)


class DeadLetterEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_outbox = models.OneToOneField(
        EventOutbox,
        on_delete=models.PROTECT,
        related_name="dead_letter",
    )
    event_type = models.CharField(max_length=128)
    event_version = models.PositiveIntegerField()
    tenant = models.ForeignKey(
        School,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="dead_letter_events",
    )
    reason = models.CharField(max_length=255)
    sanitized_error = models.CharField(max_length=255, blank=True)
    failed_after_attempts = models.PositiveIntegerField()
    moved_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self) -> None:
        super().clean()
        reject_sensitive_payload(
            {"reason": self.reason, "sanitized_error": self.sanitized_error}
        )

    def save(self, *args: Any, **kwargs: Any) -> Any:
        self.full_clean()
        return super().save(*args, **kwargs)


class AuditEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        School,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="audit_events",
    )
    actor_id = models.UUIDField(null=True, blank=True)
    action = models.CharField(max_length=128)
    resource_type = models.CharField(max_length=128)
    resource_id = models.CharField(max_length=128)
    event_outbox = models.ForeignKey(
        EventOutbox,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="audit_events",
    )
    old_state_hash = models.CharField(max_length=96, blank=True)
    new_state_hash = models.CharField(max_length=96, blank=True)
    correlation_id = models.UUIDField(default=uuid.uuid4, db_index=True)
    causation_id = models.UUIDField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    occurred_at = models.DateTimeField(default=timezone.now, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["tenant", "occurred_at"],
                name="events_audit_tenant_idx",
            ),
            models.Index(
                fields=["resource_type", "resource_id"],
                name="events_audit_resource_idx",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        reject_sensitive_payload(
            {
                "action": self.action,
                "resource_type": self.resource_type,
                "resource_id": self.resource_id,
                "user_agent": self.user_agent,
            }
        )

    def save(self, *args: Any, **kwargs: Any) -> Any:
        if not self._state.adding:
            raise ValidationError({"audit": "Audit events are append-only."})
        self.full_clean()
        return super().save(*args, **kwargs)
