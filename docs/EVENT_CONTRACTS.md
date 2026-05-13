# Event Contracts

Event contracts are registered in `EventTypeRegistry`. A contract defines the
event type, version, source module, allowed producers, allowed consumers,
tenant requirement, payload schema, priority, and retention period.

## Initial Contracts

- `tenant.school_provisioned.v1`
- `core.role_assigned.v1`
- `academics.academic_year_activated.v1`
- `curriculum.version_published.v1`
- `curriculum.diff_created.v1`
- `regulatory.notice_verified.v1`
- `teacher.readiness_requirement_created.v1`
- `principal.notification_issued.v1`
- `school.update_acknowledged.v1`

## Contract Rules

Unknown event types are rejected. Inactive event types are rejected. Producers
must be allowlisted. Tenant-scoped contracts require a tenant. Payloads must
match required fields and stay small.

Contract changes should create a new version instead of changing the meaning of
an existing event.

## Algorithm Enforcement

Contract checks are enforced through the event algorithm layer. New contracts
must stay compatible with `docs/EVENT_ALGORITHMS.md`: fact-shaped names,
exact producer allowlists, tenant requirements where applicable, small
reference-only payloads, and deterministic idempotency keys.
