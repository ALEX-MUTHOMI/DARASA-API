from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from events.algorithms.audit_hash import hash_state
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
from events.algorithms.event_contract_validator import validate_event_contract
from events.algorithms.event_type_normalizer import (
    build_event_name,
    normalize_event_name,
)
from events.algorithms.idempotency_key_builder import build_idempotency_key
from events.algorithms.partition_key_builder import build_partition_key
from events.algorithms.payload_safety_guard import (
    reject_sensitive_payload,
    validate_payload_size,
)
from events.algorithms.payload_schema_validator import validate_payload_schema
from events.algorithms.priority_ordering import sort_events_for_dispatch
from events.algorithms.producer_authorizer import authorize_producer
from events.algorithms.retry_policy import RETRYABLE, decide_retry


pytestmark = pytest.mark.phase5


def _contract(**overrides):
    contract = {
        "event_type": "curriculum.version_published",
        "event_version": 1,
        "allowed_producers": ["curriculum"],
        "requires_tenant": False,
        "payload_schema": {"required": ["curriculum_version_id"]},
        "is_active": True,
    }
    contract.update(overrides)
    return contract


def _event(**overrides):
    now = timezone.now()
    data = {
        "priority": "normal",
        "occurred_at": now,
        "available_at": now,
        "locked_at": None,
        "status": "pending",
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_event_type_normalization_accepts_facts_and_rejects_commands():
    normalized = normalize_event_name("curriculum.version_published.v1")

    assert normalized.event_type == "curriculum.version_published"
    assert normalized.event_version == 1
    assert build_event_name("principal.notification_issued", 1).endswith(".v1")

    with pytest.raises(ValidationError):
        normalize_event_name("send_message_to_principal")
    with pytest.raises(ValidationError):
        normalize_event_name("delete_everything.v1")
    with pytest.raises(ValidationError):
        normalize_event_name("curriculum.version_published")


@pytest.mark.parametrize(
    "event_name",
    [
        "send_message_now.v1",
        "publish_now.v1",
        "delete_everything.v1",
        "update_school_now.v1",
    ],
)
def test_command_shaped_event_names_fail_closed(event_name):
    with pytest.raises(ValidationError):
        normalize_event_name(event_name)


def test_contract_validation_rejects_inactive_missing_tenant_and_payload_gaps():
    validate_event_contract(
        contract=_contract(),
        event_type="curriculum.version_published",
        event_version=1,
        producer="curriculum",
        tenant_id=None,
        payload={"curriculum_version_id": "version-id"},
        priority="high",
        max_payload_bytes=2048,
    )

    with pytest.raises(ValidationError):
        validate_event_contract(
            contract=_contract(is_active=False),
            event_type="curriculum.version_published",
            event_version=1,
            producer="curriculum",
            tenant_id=None,
            payload={"curriculum_version_id": "version-id"},
            priority="high",
            max_payload_bytes=2048,
        )
    with pytest.raises(ValidationError):
        validate_event_contract(
            contract=_contract(requires_tenant=True),
            event_type="curriculum.version_published",
            event_version=1,
            producer="curriculum",
            tenant_id=None,
            payload={"curriculum_version_id": "version-id"},
            priority="high",
            max_payload_bytes=2048,
        )
    with pytest.raises(ValidationError):
        validate_event_contract(
            contract=_contract(),
            event_type="curriculum.version_published",
            event_version=1,
            producer="curriculum",
            tenant_id=None,
            payload={},
            priority="high",
            max_payload_bytes=2048,
        )


def test_producer_authorization_is_exact_and_fails_closed():
    assert authorize_producer(
        producer="curriculum",
        allowed_producers=["curriculum"],
    ) == "curriculum"

    with pytest.raises(ValidationError):
        authorize_producer(producer="academics", allowed_producers=["curriculum"])
    with pytest.raises(ValidationError):
        authorize_producer(
            producer="curriculum.extra",
            allowed_producers=["curriculum"],
        )


def test_payload_schema_and_safety_reject_bad_shapes_and_sensitive_data():
    validate_payload_schema(
        payload={"publication_id": "pub-1"},
        payload_schema={
            "required": ["publication_id"],
            "types": {"publication_id": "str"},
        },
    )

    with pytest.raises(ValidationError):
        validate_payload_schema(
            payload={"publication_id": object()},
            payload_schema={"required": ["publication_id"]},
        )
    with pytest.raises(ValidationError):
        validate_payload_schema(payload={}, payload_schema={"required": ["id"]})
    with pytest.raises(ValidationError):
        reject_sensitive_payload({"nested": {"password": "hidden"}})
    with pytest.raises(ValidationError):
        reject_sensitive_payload({"learner_names": ["Jane Doe"]})
    with pytest.raises(ValidationError):
        reject_sensitive_payload({"student_names": ["Jane Doe"]})
    with pytest.raises(ValidationError):
        reject_sensitive_payload({"guardian_phone": "+254700000000"})
    with pytest.raises(ValidationError):
        reject_sensitive_payload({"raw_curriculum_text": "full source text"})
    with pytest.raises(ValidationError):
        reject_sensitive_payload({"raw_uploaded_file": "binary-content"})
    with pytest.raises(ValidationError):
        reject_sensitive_payload({"teacher_private_notes": "sensitive note"})
    with pytest.raises(ValidationError):
        validate_payload_size({"data": "x" * 50}, max_bytes=10)


def test_idempotency_partition_and_audit_hash_are_deterministic():
    first = build_idempotency_key(
        tenant_id="school-1",
        event_type="curriculum.version_published",
        event_version=1,
        resource_type="publication",
        resource_id="pub-1",
        semantic_action="issued",
    )
    second = build_idempotency_key(
        tenant_id="school-1",
        event_type="curriculum.version_published",
        event_version=1,
        resource_type="publication",
        resource_id="pub-1",
        semantic_action="issued",
    )

    assert first == second
    assert "pub-1" in first
    assert build_partition_key(tenant_id="school-1") == "tenant:school-1"
    assert build_partition_key(event_type="curriculum.diff_created").startswith(
        "event_type:"
    )
    assert hash_state({"b": 2, "a": 1}) == hash_state({"a": 1, "b": 2})
    assert hash_state({"a": 1}) != hash_state({"a": 2})

    with pytest.raises(ValidationError):
        build_idempotency_key(
            tenant_id="",
            event_type="curriculum.version_published",
            event_version=1,
            resource_type="publication",
            resource_id="pub-1",
            semantic_action="issued",
        )
    with pytest.raises(ValidationError):
        build_partition_key(requires_tenant=True)


def test_consumer_retry_backoff_and_dead_letter_decisions_are_bounded():
    assert should_skip_consumer(status="processed")
    assert should_skip_consumer(status="started")
    assert not should_skip_consumer(status="failed")

    with pytest.raises(ValidationError):
        ensure_consumer_tenant_matches(
            event_tenant_id="school-1",
            consumer_tenant_id="school-2",
        )

    decision = decide_retry(
        failure_class=RETRYABLE,
        attempt_number=1,
        max_attempts=3,
    )
    exhausted = decide_retry(
        failure_class=RETRYABLE,
        attempt_number=3,
        max_attempts=3,
    )
    assert decision.should_retry
    assert exhausted.should_dead_letter
    assert calculate_backoff_seconds(
        attempt_number=5,
        base_delay_seconds=60,
        max_delay_seconds=300,
    ) == 300
    assert classify_dead_letter_reason(
        failure_class=RETRYABLE,
        attempt_number=3,
        max_attempts=3,
    ) == "max_retries_exceeded"
    assert sanitize_dead_letter_text("password=hidden") == "sanitized_dead_letter"


def test_priority_ordering_and_batch_planner_are_bounded_and_lock_safe():
    now = timezone.now()
    older = now - timedelta(minutes=10)
    fresh_lock = now - timedelta(seconds=5)
    stale_lock = now - timedelta(minutes=10)
    low = _event(priority="low", occurred_at=older, available_at=older)
    critical = _event(priority="critical", occurred_at=now, available_at=older)
    high_old = _event(priority="high", occurred_at=older, available_at=older)
    high_new = _event(priority="high", occurred_at=now, available_at=older)
    locked = _event(
        status="locked",
        locked_at=fresh_lock,
        priority="critical",
        available_at=older,
    )
    stale = _event(
        status="locked",
        locked_at=stale_lock,
        priority="normal",
        available_at=older,
    )

    assert sort_events_for_dispatch([low, high_new, critical, high_old]) == [
        critical,
        high_old,
        high_new,
        low,
    ]

    planned = plan_dispatch_batch(
        events=[low, critical, locked, stale],
        max_batch_size=2,
        now=now,
        lock_timeout_seconds=60,
    )

    assert planned == [critical, stale]
    assert locked not in planned


def test_event_algorithm_modules_are_side_effect_free():
    algorithms_dir = Path(__file__).resolve().parents[1] / "algorithms"
    blocked_tokens = [
        "from events.models",
        "import events.models",
        ".objects.",
        ".save(",
        ".create(",
        "requests.",
        "httpx",
        "aiohttp",
        "boto" + "3",
        "Event" + "Bridge",
        "Kaf" + "ka",
        "Kine" + "sis",
        "Kuber" + "netes",
    ]

    for module_path in algorithms_dir.glob("*.py"):
        text = module_path.read_text()
        for token in blocked_tokens:
            assert token not in text, f"{module_path.name} contains {token}"
