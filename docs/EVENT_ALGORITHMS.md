# Event Algorithms

Phase 5B makes the event backbone algorithm-first. The database stores event
facts, but deterministic functions decide whether a fact is valid, safe,
idempotent, retryable, partitionable, and auditable.

## Why This Layer Exists

Event infrastructure fails dangerously when critical rules are scattered across
services. Darasa keeps these rules in `app/events/algorithms/` so they can be
tested offline, reused by services and validators, and adapted to a future
managed broker without changing business modules.

The algorithm layer must stay side-effect-free where practical. It must not
fetch remote resources, publish to a broker, mutate Django models, or depend on
deployment infrastructure.

## Event Type Normalization

Full event names use a fact-shaped namespace plus version suffix, for example
`curriculum.version_published.v1`. Stored contracts keep the namespace and
version in separate fields, but new code should use the normalizer whenever it
accepts a complete event name.

Command-like names are rejected. Events describe what happened; they do not
tell a worker what to do next.

## Contract Validation

Contract validation checks the registered event type, version, active state,
producer allowlist, tenant requirement, payload schema, priority, size, and
payload safety. Unknown or inactive contracts fail closed.

## Producer Allowlisting

Only exact allowlist matches may emit a contract. Namespace shortcuts and broad
wildcards are intentionally avoided because they would let unrelated code paths
spoof trusted facts.

## Payload Safety

Payloads must be small JSON objects containing references. The safety guard
recursively rejects obvious secrets, raw learner data, raw documents, admission
number patterns, and credential-like fields. Payload size is measured after
canonical JSON serialization because that is the durable representation.

## Idempotency

Idempotency keys are built from tenant, event type, version, resource, and
semantic action. The same fact produces the same key; a different resource or
action produces a different key. This lets retries be safe.

## Retry, Backoff, and Dead Letter

Transient failures retry with deterministic capped exponential backoff.
Permanent, invalid, unauthorized, schema-mismatch, and tenant-mismatch failures
move to dead letter. Dead-letter reasons are sanitized so operational records do
not copy sensitive payload values.

## Partition Keys

Tenant-scoped events default to `tenant:{id}`. Global events can use event-type
partitions. This prepares Darasa for future routing by tenant, event type,
region, and priority while keeping Phase 5 local-first.

## Audit Hashing

Audit rows store references and hashes, not raw sensitive states. The audit hash
algorithm canonicalizes JSON and computes SHA-256 so the same state has the
same integrity fingerprint without exposing the source data.

## Dispatch Batch Planning

The batch planner selects a bounded set of ready events, skips fresh locks,
allows stale lock recovery, and orders by priority then age. The service layer
performs database updates after the plan is computed.

## Adding a New Event Safely

1. Define or register a versioned contract.
2. Add required payload fields and keep payloads reference-only.
3. Add the exact producer and consumer names.
4. Use algorithm helpers for event names, idempotency keys, partition keys, and
   payload validation.
5. Add direct algorithm tests and service-level tests.
6. Do not add event safety logic directly in services if it belongs in the
   deterministic algorithm layer.

