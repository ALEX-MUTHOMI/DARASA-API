# Grading Engine

Phase 6A activates the grading core foundation. It does not build the full
teacher submission workflow, reports, PDFs, parent views, or generated remarks.

## CBE/CCT Binding

CCT is Darasa's curriculum truth layer. It decides which official curriculum
version, learning area, and rubric foundation are approved and published.
Grading consumes that stored context; it does not invent CBE rules or resolve
official sources during mark entry.

Draft assessments may be incomplete so academic teams can prepare work in
progress. Operational assessments (`open`, `locked`, `submitted`, `approved`,
or `archived`) must be bound to a published curriculum version, learning area,
and rubric foundation. When an assessment becomes operational, Darasa stores a
binding timestamp so old grade records remain tied to the assessment context
that existed when grading began. Later CCT updates do not mutate old
assessments or grade records.

Publication is not enough for new grading work. CCT records explicit
tenant-specific school adoption, and new operational assessments require both
published curriculum truth and school adoption. Withdrawn curriculum versions
cannot be used for new assessment bindings. Existing operational assessments
keep their historical context after withdrawal or rollback planning.

The teacher grade-entry selector returns only assigned, open, CBE/CCT-bound
assessments. Draft management belongs on a separate future read path; it must
not be mixed with grade entry.

## Why Grading Is Batch-Based

Grades are sensitive academic records. Darasa treats a teacher submission as a
batch so future services can validate roster membership, teacher assignment,
assessment status, record count, idempotency, and audit evidence once per
submission instead of emitting one event per score.

## Phase 6B Grade Grid Workflow

Phase 6B adds the backend contract for the teacher-facing marksheet:

1. `get_my_grading_work` returns assigned, open, CBE/CCT-bound assessments only.
2. `build_grade_grid` returns structured metadata, roster rows, draft values,
   submitted values, validation rules, and component columns. It is not HTML.
3. `save_grade_draft` stores editable teacher-owned drafts. Drafts are not
   official grade records.
4. `submit_grade_batch` requires step-up confirmation, validates the roster and
   score bounds, commits official `GradeRecord` rows transactionally, and emits
   one compact batch-level event after commit.

Slow-network retries use idempotency keys and payload hashes. Stale draft
versions are rejected so two browser sessions cannot silently overwrite newer
work.

Drafts are sensitive because they can contain provisional marks. They are owned
by one tenant, teacher, and assessment, and are never official `GradeRecord`
rows until final submission succeeds. They must not appear in events. Before
production, Darasa needs an explicit draft retention policy that expires or
archives abandoned drafts by tenant, assessment, and age; only the owning
teacher or a future explicitly authorized reviewer workflow may inspect them.

Practical and CBE-style assessments can define `AssessmentComponent` rows for
component columns. Component scores are validated against component maximums and
the assessment maximum. Phase 6B does not compile final summaries.

## ABAC, Not RBAC Only

A role such as subject teacher is not enough. The backend must also prove the
teacher is actively assigned to the assessment cohort and learning area in the
same tenant, academic year, and term. Missing tenant, actor, role, assessment,
or assignment fails closed.

## Academic Record Integrity

Phase 6A introduces:

- `Assessment`: tenant-scoped assessment context and lifecycle.
- `GradeSubmissionBatch`: teacher, assignment, cohort, learning area, and
  idempotency boundary for future submissions.
- `GradeRecord`: one learner score per assessment within a tenant.
- `GradeCorrectionRequest`: auditable correction workflow with old-state hash.

Submitted grades must not be silently overwritten. Corrections are requested,
reviewed, approved or rejected, and kept auditable. Phase 6A does not mutate
grade records automatically from correction requests.

## Event Safety

Phase 6B emits `grading.batch_submitted` only after a successful transaction.
The event is one fact per batch, not one event per learner. It carries
identifiers, record count, and submission time only. It must not contain raw
marks, component scores, learner names, guardian data, private teacher notes,
full reports, or raw grade grids.

## Phase 6C Compilation

Compilation is deterministic data preparation, not report generation. Phase 6C
compiles submitted official grade records into canonical learner snapshots,
assessment snapshots, and cohort / learning-area summaries. Drafts are ignored.
The compiler uses the stored assessment CBE/CCT context; it does not call CCT
source validation, web logic, or curriculum diffing per learner or mark.

Role-aware projections are views over the same compiled facts. Teacher, HOD,
deputy/head, principal, and future parent-safe projections may filter and shape
data, but they must not create separate academic truth. Future parent
projection foundations are learner-specific and exclude drafts, internal review
notes, unapproved corrections, and school-wide analytics. Until an explicit
guardian-learner relationship model exists, parent projections fail closed even
for users with a guardian role.

## Phase 6D Readiness Projections

Phase 6D is the backend readiness layer before reports. It asks whether a
tenant, department, cohort, learning area, or assessment can safely proceed
toward report generation. It consumes Phase 6B submitted grade batches, Phase
6C compiled snapshots, teacher assignment context, and CCT adoption /
withdrawal / rollback / app-impact state.

Readiness is not a second compiler. It interprets the compiled facts and
records blockers such as missing marks, missing required components,
unsubmitted teacher batches, drafts without final submission, failed or stale
compilations, pending corrections, CCT adoption gaps, withdrawals, rollback
review, and app-impact review. It must not mutate `GradeRecord`,
`GradeSubmissionBatch`, `CompilationRun`, compiled snapshots, or stored
CBE/CCT assessment bindings.

Teacher readiness is assignment-scoped. HOD readiness is department or
learning-area scoped through teacher assignment. Deputy/head-of-academics
readiness is tenant academic-operations scoped. Principal readiness is tenant
executive-readiness scoped. Future parent readiness remains a fail-closed
foundation until approved release data and guardian relationships exist; it
must not expose drafts, internal corrections, teacher private notes, school-wide
analytics, other learners' data, or unapproved compilations.

CCT blockers are review and safety signals. A withdrawal or rollback review can
block report readiness for future action, but it does not rewrite historical
assessments, submitted grades, or compiled snapshots.

CCT app-impact readiness blockers are tenant scoped, app-domain scoped, and
matched against available assessment scope such as county metadata, pathway,
grade level, learning area, and rubric. `scope_unknown` remains conservative
and requires review. A scoped CCT impact for an unrelated county, learning
area, or non-grading app domain must not block unrelated readiness.

Darasa does not yet have a separate Phase 6E moderation workflow model. Phase
6D blocks on pending correction requests and keeps moderation statuses as
readiness vocabulary for the next grading phase; once moderation records exist,
pending moderation must be a computed blocker rather than a client override.

## Phase Boundaries

Compilation is separate from readiness, and readiness is separate from report
generation. Phase 6C compiles canonical facts. Phase 6D projects operational
readiness over those facts. Report generation and PDFs belong to Phase 7. Safe
NLP boundaries remain Phase 9 or later and cannot decide academic records.

NLP or generated text must never decide grades. Human academic records remain
database-backed, auditable, tenant-scoped, and policy-controlled.

## Production Readiness Backlog

`PRODUCTION_READINESS_BACKLOG.md` records grading work that remains before
national production rollout. Phase 6D adds readiness dashboards / report-ready
projections, but it is still not a report generator. Reports, PDFs, parent
analytics, and NLP remain later phases. Grading production blockers include
large-roster performance profiling, stale compilation operations, correction
workflow hardening, teacher workload stress testing, production step-up
integration, audit expansion, and frontend retry/idempotency behavior.
