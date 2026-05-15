"""Constants for the local event backbone.

Phase 5 stores events in Postgres first.  The limits here keep that local
outbox safe: small payloads, bounded retries, bounded relay batches, and stable
priorities that can later map to a managed broker without changing producers.
"""

from __future__ import annotations


MAX_EVENT_PAYLOAD_BYTES = 8 * 1024
MAX_RETRY_ATTEMPTS = 3
DEFAULT_RETRY_DELAY_SECONDS = 60
MAX_RELAY_BATCH_SIZE = 100
LOCK_TIMEOUT_SECONDS = 300
EVENT_PRIORITIES = frozenset({"critical", "high", "normal", "low", "background"})
PRIORITY_ORDER = {
    "critical": 0,
    "high": 1,
    "normal": 2,
    "low": 3,
    "background": 4,
}

INITIAL_EVENT_CONTRACTS = [
    {
        "event_type": "tenant.school_provisioned",
        "event_version": 1,
        "description": "A school tenant was provisioned.",
        "source_module": "tenant",
        "allowed_producers": ["tenant"],
        "allowed_consumers": ["audit"],
        "requires_tenant": True,
        "payload_schema": {"required": ["school_id"]},
        "priority": "high",
    },
    {
        "event_type": "core.role_assigned",
        "event_version": 1,
        "description": "A tenant-scoped role binding was assigned.",
        "source_module": "core",
        "allowed_producers": ["core", "tenant"],
        "allowed_consumers": ["audit"],
        "requires_tenant": True,
        "payload_schema": {"required": ["user_id", "role_code"]},
        "priority": "normal",
    },
    {
        "event_type": "academics.academic_year_activated",
        "event_version": 1,
        "description": "A tenant academic year became active.",
        "source_module": "academics",
        "allowed_producers": ["academics"],
        "allowed_consumers": ["audit"],
        "requires_tenant": True,
        "payload_schema": {"required": ["academic_year_id"]},
        "priority": "normal",
    },
    {
        "event_type": "curriculum.version_published",
        "event_version": 1,
        "description": "A curriculum version was published after review.",
        "source_module": "curriculum",
        "allowed_producers": ["curriculum"],
        "allowed_consumers": ["audit"],
        "requires_tenant": False,
        "payload_schema": {"required": ["curriculum_version_id"]},
        "priority": "high",
    },
    {
        "event_type": "curriculum.diff_created",
        "event_version": 1,
        "description": "A curriculum diff was created for review.",
        "source_module": "curriculum",
        "allowed_producers": ["curriculum"],
        "allowed_consumers": ["audit"],
        "requires_tenant": False,
        "payload_schema": {"required": ["curriculum_diff_id"]},
        "priority": "normal",
    },
    {
        "event_type": "regulatory.notice_verified",
        "event_version": 1,
        "description": "A regulatory notice was verified from official evidence.",
        "source_module": "curriculum",
        "allowed_producers": ["curriculum"],
        "allowed_consumers": ["audit"],
        "requires_tenant": False,
        "payload_schema": {"required": ["regulatory_notice_id"]},
        "priority": "high",
    },
    {
        "event_type": "teacher.readiness_requirement_created",
        "event_version": 1,
        "description": "A teacher readiness requirement was recorded.",
        "source_module": "curriculum",
        "allowed_producers": ["curriculum"],
        "allowed_consumers": ["audit"],
        "requires_tenant": False,
        "payload_schema": {"required": ["teacher_readiness_requirement_id"]},
        "priority": "normal",
    },
    {
        "event_type": "principal.notification_issued",
        "event_version": 1,
        "description": "A principal evidence card was issued to a school.",
        "source_module": "curriculum",
        "allowed_producers": ["curriculum"],
        "allowed_consumers": ["audit"],
        "requires_tenant": True,
        "payload_schema": {"required": ["notification_id"]},
        "priority": "high",
    },
    {
        "event_type": "school.update_acknowledged",
        "event_version": 1,
        "description": "A school acknowledged an update evidence card.",
        "source_module": "curriculum",
        "allowed_producers": ["curriculum"],
        "allowed_consumers": ["audit"],
        "requires_tenant": True,
        "payload_schema": {"required": ["acknowledgement_id"]},
        "priority": "normal",
    },
    {
        "event_type": "grading.batch_submitted",
        "event_version": 1,
        "description": "A teacher submitted one CBE-bound grading batch.",
        "source_module": "grading",
        "allowed_producers": ["grading"],
        "allowed_consumers": ["audit"],
        "requires_tenant": True,
        "payload_schema": {
            "required": [
                "tenant_id",
                "assessment_id",
                "batch_id",
                "cohort_id",
                "learning_area_id",
                "curriculum_version_id",
                "record_count",
                "submitted_at",
            ]
        },
        "priority": "normal",
    },
]
