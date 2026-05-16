# Developer Event Guide

Use the event backbone when a module needs to record an important fact for
audit or later reaction.

## Adding an Event Type

1. Add or register a new `EventTypeRegistry` contract.
2. Use a fact-shaped name like `principal.notification_issued`.
3. Set a version number.
4. Define the source module and allowlisted producers.
5. Define required payload fields.
6. Decide whether tenant context is required.
7. Add tests for unknown type rejection, producer rejection, tenant requirement,
   idempotency, and payload validation.
8. Update algorithm tests if the contract needs a new validation rule.

## Emitting an Event

Use `events.services.write_outbox_event`. Do not create `EventOutbox` rows
directly from business code. The service validates the contract, producer,
tenant, partition key, idempotency key, payload size, and sensitive fields.

Use `events.algorithms.idempotency_key_builder` and
`events.algorithms.partition_key_builder` for new producers. Do not duplicate
those rules in business services.

## Adding a Consumer

Register an internal handler with a consumer name. Consumers must be idempotent:
check consumer state, record started, process, record processed, and record
failure without leaking raw payloads. Poison events must move to dead letter
after bounded retries.

## Algorithm Rule

If a rule decides whether an event is safe, retryable, idempotent, tenant-safe,
or dispatchable, put it in `app/events/algorithms/` first. Services should
orchestrate database writes around those deterministic decisions.

See `docs/EVENT_ALGORITHMS.md` for the supported algorithm modules.

## Grading Event Readiness

Phase 6B emits `grading.batch_submitted` after a successful final grade batch
transaction. Grading payloads must stay compact: tenant, assessment, batch,
cohort, learning area, curriculum version, rubric foundation, record count, and
submission time only. Do not put raw marks, component scores, learner names,
guardian data, teacher private notes, report text, or raw grade grids into
events.

Phase 6C emits `grading.compilation_completed` after a deterministic
compilation transaction commits. The payload is reference-only: tenant,
assessment, compilation run, cohort, learning area, curriculum version, status,
and compiled time. Do not emit one event per learner, component, or score.

## Ownership

Changes under `app/events`, event docs, CI, Docker, settings, and scripts should
be reviewed by a platform/security owner before merge.
