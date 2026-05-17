# Darasa-Core Security Model

Darasa-Core uses tenant-scoped RBAC plus ABAC checks.

RBAC answers which broad role a user has. ABAC answers whether that user can
act on a specific tenant, resource, assignment, or evidence record. Missing
tenant, missing actor, inactive actor, missing role, inactive role, unknown
action, or inactive tenant binding denies access.

## Tenant Isolation

Tenant isolation is the primary boundary. Selectors and policies must filter by
school tenant whenever they read school-owned data. A user with a role in one
school does not gain authority in another school.

## Academic Data

Learner records are sensitive. Academic policies require an active tenant role,
and teacher access depends on active cohort and learning-area assignments. A
teacher does not get broad learner access by being a teacher globally.

## Curriculum Governance

Curriculum records are not learner records, but curriculum governance still
affects school operations. Source registration, review, publication, principal
notification, and acknowledgement are separate operations. This prevents
mass-assignment shortcuts and preserves audit evidence.

CCT distinguishes detected, quarantined, verified, published, school-adopted,
withdrawn, and rolled-back states. A national publication is not a tenant
activation. Schools must schedule or activate adoption explicitly, and new
grading bindings fail closed unless the tenant has adopted the published
version. Withdrawals block new adoption but do not mutate old assessments,
grade records, or compiled snapshots.

Curriculum rollout and notice issuance must be batchable. CCT may create
principal evidence cards, teacher readiness notices, adoption records,
withdrawal records, rollback plans, and notice batch runs; it must not fan out
unbounded synchronous work to all schools or all learners.

## Secrets and PII

Production secrets must come from environment variables. Fernet configuration is
validated at startup so encrypted-field behavior cannot silently degrade.

Governance text rejects obvious learner-specific PII patterns. This keeps
curriculum updates, regulatory notices, evidence cards, and acknowledgement
notes from becoming accidental child-data stores.

## Event Backbone

Events are typed, versioned facts. Producers are allowlisted, tenant-scoped
events require tenant context, idempotency keys are mandatory, and payloads are
kept small and screened for obvious sensitive fields. Consumers record state so
duplicate processing is skipped safely, and poison events move to dead letter
instead of retrying forever.

The event safety rules are implemented in `app/events/algorithms/` and
documented in `EVENT_ALGORITHMS.md`. Services must delegate security-critical
event decisions there instead of reimplementing them inline.

## Grading Records

Grades are sensitive academic records. Phase 6A requires tenant-scoped
assessments, active teacher assignments for grading access, one active record
per learner and assessment, score bounds, and auditable correction requests.
RBAC grants broad capability; ABAC proves the teacher is assigned to the exact
cohort and learning area. Grade events must carry references and counts, not raw
marks or learner names.

Phase 6A.1 adds CBE/CCT binding as a grading invariant. Draft assessments may
be incomplete, but operational grading requires a stored published curriculum
version, learning area, and rubric foundation. Grade-entry selectors expose only
assigned, open, bound assessments. Grade records use the stored assessment
context and do not call CCT source or web validation per score.

Phase 6B adds teacher workflow safeguards: draft rows are editable but not
official records, final submission requires step-up confirmation, idempotency
keys prevent duplicate retries, payload hashes prevent same-key mutation, and
one compact event is emitted per submitted batch after commit. Draft retention
is a production-readiness requirement: abandoned drafts must be expired or
archived by tenant, assessment, and age before schools rely on the workflow at
scale.

Phase 6C compiles official submitted records into canonical snapshots and
role-aware projections. Compilation does not generate reports, PDFs, parent
portal responses, or NLP text. Projections must derive from the same compiled
facts and remain tenant/policy scoped; they may filter and shape data, but they
must not recalculate academic meaning per role. HOD compilation visibility is
assignment-scoped until a department ownership model exists. Future parent
projection remains fail-closed until guardian-learner mapping is modeled.

After CCT fortification, grading and compilation consume CCT through explicit
dependency guards. Future reports must consume compiled snapshots with their
preserved curriculum context instead of re-resolving live curriculum truth.
