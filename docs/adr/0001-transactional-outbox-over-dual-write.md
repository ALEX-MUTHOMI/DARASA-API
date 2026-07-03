# ADR 0001: Transactional outbox instead of dual-write

## Status

Accepted. Implemented in Phase 5 / 5B (`app/events`).

## Context

Darasa needs other parts of the system (and, later, other services) to react
to facts such as "a grade batch was submitted" or "a curriculum version was
published" without those domains calling into each other's write paths
directly (that would violate the DDD boundary: no cross-domain writes).

The naive approach — commit the domain write, then publish a message to
Redis/Celery — is a **dual write**. If the process crashes, is killed, or the
broker is unreachable between the two operations, the domain change and the
event fall out of sync: either an event is lost even though the domain change
happened, or an event fires for a domain change that never committed.

## Decision

Write the event envelope into a Postgres `Outbox` table **in the same
database transaction** as the domain write. A separate relay/dispatcher reads
undispatched outbox rows and hands them to consumers (currently in-process;
later, potentially an external broker) after the transaction has already
committed.

This makes "domain state changed" and "an event exists describing it"
atomic, because they are the same Postgres transaction. The dispatch step can
fail and retry independently without ever risking data loss or a phantom
event.

## Consequences

- Events are **facts**, not commands, and are inherently at-least-once:
  consumers must be idempotent (`app/events/algorithms` enforces this
  deterministically — see `docs/EVENT_ALGORITHMS.md`).
- There is dispatch latency between commit and delivery (bounded by the
  relay's polling/batch interval), which is acceptable because Darasa is
  explicitly "reliable-first," not real-time-first (see
  `docs/EVENT_BACKBONE.md`).
- The outbox table itself becomes a new piece of infrastructure to monitor
  (backlog depth, age, dead letters) — tracked as `EVT-P0-001` and
  `EVT-P0-002` in `docs/PRODUCTION_READINESS_BACKLOG.md`.
- Migrating to an external broker (Kafka/SQS/Kinesis) later does not require
  re-architecting the write path: the broker adapter sits behind the existing
  dispatcher boundary and the outbox stays the source of truth
  (`EVT-P3-010`).
