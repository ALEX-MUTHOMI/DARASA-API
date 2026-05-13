import uuid
from pathlib import Path

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from core.models import Role, TenantUserRole
from core.policies import PolicyContext
from events.constants import INITIAL_EVENT_CONTRACTS, MAX_RETRY_ATTEMPTS
from events.handlers import clear_handlers, register_handler
from events.models import (
    DeadLetterEvent,
    EventConsumerState,
    EventOutbox,
    EventTypeRegistry,
)
from events.policies import (
    can_register_event_type,
    can_view_audit_events,
    can_view_dead_letter_events,
    can_view_event_backlog,
)
from events.selectors import (
    get_audit_events_for_resource,
    get_audit_events_for_tenant,
    get_dead_letter_events,
    get_dispatch_attempts_for_event,
    get_event_backlog_summary,
    get_oldest_pending_event_age,
    get_pending_outbox_events,
)
from events.services import (
    PermanentEventError,
    RetryableEventError,
    already_processed,
    dispatch_pending_events,
    lock_pending_events,
    record_audit_event,
    record_consumer_failed,
    record_consumer_processed,
    record_consumer_started,
    register_event_type,
    write_outbox_event,
)
from tenant.models import School


pytestmark = [pytest.mark.django_db, pytest.mark.phase5]


@pytest.fixture
def app_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _school(label: str = "events") -> School:
    token = uuid.uuid4().hex[:8]
    return School.objects.create(
        name=f"{label} school {token}",
        schema_name=f"{label}_{token}",
        subdomain=f"{label}-{token}",
        school_code=f"E{token[:7]}".upper(),
    )


def _principal(school: School):
    role, _ = Role.objects.get_or_create(
        code=Role.RoleCode.PRINCIPAL,
        defaults={"name": Role.RoleCode.PRINCIPAL.label},
    )
    from core.models import CustomUser

    user = CustomUser.objects.create_user(
        email=f"event-principal-{uuid.uuid4().hex[:8]}@example.test",
        password="test-only-secret",
    )
    TenantUserRole.objects.create(user=user, tenant=school, role=role)
    return user, role


def _event(
    *,
    tenant: School | None = None,
    event_type: str = "tenant.school_provisioned",
    producer: str = "tenant",
    key: str | None = None,
    payload: dict | None = None,
    priority: str | None = None,
) -> EventOutbox:
    return write_outbox_event(
        event_type=event_type,
        event_version=1,
        source_module=producer,
        idempotency_key=key or uuid.uuid4().hex,
        tenant=tenant,
        payload=payload or {"school_id": str(tenant.id if tenant else uuid.uuid4())},
        priority=priority,
    )


def test_initial_event_contracts_are_registered():
    registered = set(EventTypeRegistry.objects.values_list("event_type", flat=True))

    assert {contract["event_type"] for contract in INITIAL_EVENT_CONTRACTS}.issubset(
        registered
    )
    for registry in EventTypeRegistry.objects.all():
        assert registry._meta.pk.__class__.__name__ == "UUIDField"


def test_registry_rejects_duplicate_inactive_unknown_and_invalid_events():
    with pytest.raises((IntegrityError, ValidationError)):
        with transaction.atomic():
            register_event_type(
                event_type="tenant.school_provisioned",
                event_version=1,
                description="Duplicate.",
                source_module="tenant",
                allowed_producers=["tenant"],
                allowed_consumers=["audit"],
                requires_tenant=True,
                payload_schema={"required": ["school_id"]},
            )

    registry = EventTypeRegistry.objects.get(event_type="tenant.school_provisioned")
    registry.is_active = False
    registry.save(update_fields=["is_active"])
    with pytest.raises(EventTypeRegistry.DoesNotExist):
        write_outbox_event(
            event_type="tenant.school_provisioned",
            event_version=1,
            source_module="tenant",
            idempotency_key=uuid.uuid4().hex,
            tenant=_school(),
            payload={"school_id": str(uuid.uuid4())},
        )

    with pytest.raises(EventTypeRegistry.DoesNotExist):
        write_outbox_event(
            event_type="tenant.unknown_fact",
            event_version=1,
            source_module="tenant",
            idempotency_key=uuid.uuid4().hex,
            tenant=_school("unknown"),
            payload={"school_id": str(uuid.uuid4())},
        )

    with pytest.raises(ValidationError):
        register_event_type(
            event_type="send_message_to_principal_now",
            event_version=1,
            description="Invalid command-shaped event.",
            source_module="tenant",
            allowed_producers=["tenant"],
            allowed_consumers=["audit"],
            requires_tenant=True,
            payload_schema={},
        )


def test_outbox_transaction_idempotency_payload_and_pii_controls():
    school = _school()
    key = uuid.uuid4().hex

    with pytest.raises(RuntimeError):
        with transaction.atomic():
            _event(tenant=school, key="rolled-back")
            raise RuntimeError("rollback")
    assert not EventOutbox.objects.filter(idempotency_key="rolled-back").exists()

    event = _event(tenant=school, key=key)
    assert event.status == EventOutbox.Status.PENDING

    with pytest.raises((IntegrityError, ValidationError)):
        with transaction.atomic():
            _event(tenant=school, key=key)

    with pytest.raises(ValidationError):
        _event(tenant=school, payload={"school_id": str(school.id), "email": "a@b.cd"})

    with pytest.raises(ValidationError):
        _event(tenant=school, payload={"school_id": "x" * 9000})


def test_producer_allowlist_and_tenant_requirements_fail_closed():
    school = _school()

    with pytest.raises(ValidationError):
        _event(tenant=school, producer="curriculum")

    with pytest.raises(ValidationError):
        write_outbox_event(
            event_type="tenant.school_provisioned",
            event_version=1,
            source_module="tenant",
            idempotency_key=uuid.uuid4().hex,
            payload={"school_id": str(school.id)},
        )

    global_event = write_outbox_event(
        event_type="curriculum.version_published",
        event_version=1,
        source_module="curriculum",
        idempotency_key=uuid.uuid4().hex,
        payload={"curriculum_version_id": str(uuid.uuid4())},
    )
    assert global_event.tenant is None


def test_consumer_idempotency_and_tenant_mismatch_controls():
    school = _school()
    event = _event(tenant=school)

    state = record_consumer_started(event=event, consumer_name="audit")
    processed = record_consumer_processed(event=event, consumer_name="audit")

    assert state.id == processed.id
    assert already_processed(event_id=event.id, consumer_name="audit")

    with pytest.raises(ValidationError):
        record_consumer_started(
            event=event,
            consumer_name="tenant-mismatch",
            tenant=_school("other"),
        )

    failed = record_consumer_failed(
        event=event,
        consumer_name="projection",
        failure_reason="safe failure",
    )
    assert failed.status == EventConsumerState.Status.FAILED


def test_dispatch_success_duplicate_skip_and_bounded_batch():
    clear_handlers()
    school = _school()
    processed: list[uuid.UUID] = []

    def handler(event):
        processed.append(event.id)

    register_handler("tenant.school_provisioned", "audit", handler)
    first = _event(tenant=school, priority="high")
    second = _event(tenant=school, priority="low")

    assert dispatch_pending_events(batch_size=1) == 1
    first.refresh_from_db()
    second.refresh_from_db()

    assert first.status == EventOutbox.Status.DISPATCHED
    assert second.status == EventOutbox.Status.PENDING
    assert processed == [first.id]

    assert dispatch_pending_events(batch_size=10) == 1
    assert processed == [first.id, second.id]


def test_retry_policy_and_dead_letter_are_bounded_and_sanitized():
    clear_handlers()
    school = _school()

    def retryable(_event):
        raise RetryableEventError("temporary outage")

    register_handler("tenant.school_provisioned", "audit", retryable)
    event = _event(tenant=school)

    for _ in range(MAX_RETRY_ATTEMPTS):
        dispatch_pending_events()
        event.refresh_from_db()
        event.available_at = timezone.now()
        event.save(update_fields=["available_at"])

    event.refresh_from_db()
    assert event.status == EventOutbox.Status.DEAD_LETTERED
    assert (
        DeadLetterEvent.objects.get(event_outbox=event).reason
        == "max_retries_exceeded"
    )
    assert get_dispatch_attempts_for_event(event).count() == MAX_RETRY_ATTEMPTS

    clear_handlers()

    def poison(_event):
        raise PermanentEventError("invalid contract")

    register_handler("tenant.school_provisioned", "audit", poison)
    poison_event = _event(tenant=school)
    dispatch_pending_events()
    poison_event.refresh_from_db()

    assert poison_event.status == EventOutbox.Status.DEAD_LETTERED
    assert get_dead_letter_events().filter(event_outbox=poison_event).exists()


def test_audit_events_are_append_only_tenant_aware_and_pii_safe():
    school = _school()
    event = _event(tenant=school)
    audit = record_audit_event(
        tenant=school,
        action="tenant.school_provisioned",
        resource_type="school",
        resource_id=str(school.id),
        event_outbox=event,
        new_state_hash="sha256:" + "a" * 64,
    )

    assert list(get_audit_events_for_tenant(tenant=school)) == [audit]
    assert list(
        get_audit_events_for_resource(
            tenant=school,
            resource_type="school",
            resource_id=str(school.id),
        )
    ) == [audit]

    with pytest.raises(ValidationError):
        audit.action = "password exposed"
        audit.save()

    with pytest.raises(ValidationError):
        record_audit_event(
            tenant=school,
            action="unsafe",
            resource_type="learner",
            resource_id="ADM12345",
        )


def test_selectors_backlog_locking_priority_and_stale_lock_behavior():
    school = _school()
    low = _event(tenant=school, priority="low")
    high = _event(tenant=school, priority="high")

    pending = list(get_pending_outbox_events())
    assert set(pending) == {low, high}
    assert get_oldest_pending_event_age() is not None

    locked = lock_pending_events(dispatcher_name="test-relay", batch_size=1)
    assert locked == [high]
    high.refresh_from_db()
    assert high.status == EventOutbox.Status.LOCKED
    assert high.locked_by == "test-relay"
    assert get_event_backlog_summary()[EventOutbox.Status.LOCKED] == 1


def test_event_policies_fail_closed_and_inactive_role_denies():
    school = _school()
    principal, role = _principal(school)
    context = PolicyContext(
        tenant=school,
        actor=principal,
        action="events.audit.view",
        role=role,
    )

    assert can_view_audit_events(context)
    assert can_view_event_backlog(
        PolicyContext(
            tenant=school,
            actor=principal,
            action="events.backlog.view",
            role=role,
        )
    )
    assert can_view_dead_letter_events(
        PolicyContext(
            tenant=school,
            actor=principal,
            action="events.dead_letter.view",
            role=role,
        )
    )
    assert can_register_event_type(
        PolicyContext(
            tenant=school,
            actor=principal,
            action="events.registry.register",
            role=role,
        )
    )

    TenantUserRole.objects.filter(user=principal, tenant=school, role=role).update(
        is_active=False
    )
    assert not can_view_audit_events(context)


def test_phase_boundaries_and_docs_exist(app_root, settings):
    assert "events" in settings.INSTALLED_APPS
    assert "grading" not in settings.INSTALLED_APPS
    assert not (app_root / "events" / "external_broker_dispatcher.py").exists()
    assert not (app_root / "events" / "stream_broker.py").exists()
    assert not (app_root / "curriculum" / "crawler.py").exists()
    assert not (app_root / "curriculum" / "ai_parser.py").exists()

    docs_root = app_root.parent / "docs"
    assert (docs_root / "EVENT_BACKBONE.md").exists()
    assert (docs_root / "EVENT_CONTRACTS.md").exists()
    assert (docs_root / "DEVELOPER_EVENT_GUIDE.md").exists()
    assert (docs_root / "EVENT_ALGORITHMS.md").exists()
