# Event Backbone

Phase 5 introduces Darasa's local event backbone. It records important facts in
a transactional outbox so modules can react without becoming tightly coupled.

## Facts, Not Commands

An event describes something that already happened, such as a school being
provisioned or a principal evidence card being issued. It must not instruct a
worker to mutate arbitrary school state.

## Transactional Outbox

Business services write event envelopes into Postgres in the same transaction as
the domain change. A relay dispatches later. This avoids the unsafe pattern of
committing domain state and publishing to an external broker inside the same
code path.

## Local First, Broker Ready

Phase 5 dispatches to internal handlers only. The envelope carries type,
version, tenant, correlation, causation, idempotency, priority, partition key,
and small payload fields so a future managed broker adapter can be added behind
the dispatcher boundary.

## Safety Controls

Events are typed, versioned, producer-allowlisted, tenant-aware, idempotent,
size-limited, and screened for obvious sensitive payloads. Dispatch attempts,
consumer state, dead-letter records, and audit records make failures visible
without infinite retry loops.

## Algorithm Layer

Phase 5B adds `app/events/algorithms/` as the source of truth for deterministic
event safety rules. Validators and services now delegate event name checks,
contract validation, producer authorization, payload safety, idempotency,
retry/backoff decisions, dead-letter classification, partition keys, audit
hashing, and batch planning to that package.

See `docs/EVENT_ALGORITHMS.md` before adding a new event rule.
