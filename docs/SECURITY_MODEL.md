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

CCT full-proofing adds a school evidence-intake workflow. Principals, deputies,
and school administrators may submit private storage references and document
metadata, but that creates quarantined evidence only. It never publishes a
curriculum version, adopts a version for a tenant, changes grading, changes
compiled snapshots, generates reports, or notifies every school as truth.

Document verification reports score deterministic signals such as reference
numbers, publication numbers, dates, stamp/signature metadata, duplicate
clusters, authority match status, and claimed scope. These signals support
review; they are not proof. A 24-hour SLA is a review target, not an
auto-approval timer.

Governance decisions are separate and server-derived. Current approval requires
the school-admin governance role until dedicated curriculum governance roles
exist. Principals and deputies can submit evidence, but they cannot approve
curriculum truth through the full-proofing workflow; `is_staff` alone remains
irrelevant to curriculum authority.

## Secrets and PII

Production secrets must come from environment variables. Fernet configuration is
validated at startup so encrypted-field behavior cannot silently degrade.

JWT authentication is provided through SimpleJWT and PyJWT. Darasa pins the
application contract to explicit `HS256` signing, rejects `none` or unexpected
algorithms at settings validation time, and requires a strong
environment-provided `JWT_SIGNING_KEY` outside tests. Access tokens are short
lived, refresh-token rotation and blacklisting are enabled, and token claims
must remain minimal. JWT role-like claims are not an authorization source of
truth; privileged CCT, grading, correction, and tenant decisions must reload
server-side user, tenant, role-binding, assignment, and policy state.

Dependency audit remains mandatory. `PYSEC-2025-183` / `CVE-2025-45768` for
PyJWT is the only current narrow exception because the advisory is disputed,
has no fixed version, and concerns application-selected key strength. The
exception must be reviewed before production release and during dependency
update cycles; if a fixed PyJWT version becomes available, Darasa must remove
the ignore and upgrade.

Governance text rejects obvious learner-specific PII patterns. This keeps
curriculum updates, regulatory notices, evidence cards, and acknowledgement
notes from becoming accidental child-data stores.

Governance text also rejects executable HTML patterns. CCT metadata, notice
text, rollback reasons, and upload metadata remain untrusted plaintext; future
frontends must escape them and must not treat backend-stored text as safe HTML.
Future evidence uploads require private malware-scan-ready storage, checksum
fingerprinting, MIME verification, file size limits, rate limits, and audit
logs before production use.

The CCT evidence model includes explicit malware-scan and content-verification
readiness states. Those states are infrastructure-derived, not client-derived.
Governance approval for publication requires clean malware status and passed
content verification; a high confidence document report, stamp signal,
signature signal, duplicate cluster, or expired 24-hour SLA cannot override a
pending, suspicious, infected, unavailable, failed, or unsupported upload
readiness state.

Evidence submission is a production step-up action. Before public upload
endpoints exist, Darasa must bind step-up confirmation to the same actor and
tenant, expire it, rate-limit it, and avoid storing raw passwords, PINs, or
device secrets.

The production-readiness backlog in `PRODUCTION_READINESS_BACKLOG.md` records
remaining security and compliance blockers: WAF/DDoS protection, global and
tenant-aware rate limits, security headers, CSP, CSRF/session review, admin
access hardening, secret rotation, audit log immutability, PII retention, data
export controls, incident response runbooks, SAST/DAST strategy, dependency
update policy, and threat-model review.

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

Phase 6D adds readiness projections over submitted and compiled facts. These
projections identify report-readiness blockers such as missing marks, missing
required components, unsubmitted batches, draft-only work, failed or stale
compilations, pending corrections, CCT adoption gaps, withdrawals, rollback
review, and CCT app-impact review. Teacher readiness is assignment-scoped, HOD
readiness is department or learning-area scoped, deputy/head readiness is tenant
academic-operations scoped, and principal readiness is tenant executive scoped.
`is_staff` is not an academic visibility bypass. Future parent readiness remains
fail-closed until an approved release model exists.

CCT app-impact blockers must be scoped before they affect readiness. A tenant's
unknown-scope grading/report impact requires review, but an unrelated county,
learning-area, or non-grading future-app impact must not be treated as a
school-wide readiness blocker.

Readiness must not mutate `Assessment`, `GradeRecord`, `GradeSubmissionBatch`,
`CompilationRun`, compiled learner snapshots, or cohort summaries. It must not
generate reports, PDFs, parent portal responses, or NLP text.

Phase 6E treats submitted mark changes as a sensitive academic-record workflow.
Teachers request corrections for assigned assessments; HODs review only within
assigned learning-area scope; deputy/head-of-academics style roles may approve
explicit escalations; principals receive executive correction summaries but do
not casually edit marks. Teacher self-approval, inactive-role approval,
cross-tenant approval, and `is_staff` bypasses fail closed.

Correction services reject client-controlled status, reviewer, approver,
applier, tenant, and old-state fields. Text reasons are stored as untrusted
plaintext and reject executable HTML patterns. Audit records use state hashes,
changed-field names, IDs, and reason codes instead of learner names or raw
grade-grid payloads. Correction events are not emitted in Phase 6E; if future
events are added, payloads must be reference-only and must exclude raw marks,
old/new mark values, learner names, guardian data, private teacher notes, and
report text.

School internal grading schemas are tenant-scoped and versioned. They interpret
school-specific CAT, internal exam, mock, trial, departmental, and practical
score bands without changing CBE/CCT meaning. Schema binding is denied for CBE
rubric assessments, cross-tenant schemas, deprecated schemas, and mismatched
assessment types. Schema changes do not mutate historical grade records or
compiled snapshots.

After CCT fortification, grading and compilation consume CCT through explicit
dependency guards. Future reports must consume compiled snapshots with their
preserved curriculum context instead of re-resolving live curriculum truth.
