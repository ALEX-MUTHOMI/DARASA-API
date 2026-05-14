# Grading Engine

Phase 6A activates the grading core foundation. It does not build the full
teacher submission workflow, reports, PDFs, parent views, or generated remarks.

## Why Grading Is Batch-Based

Grades are sensitive academic records. Darasa treats a teacher submission as a
batch so future services can validate roster membership, teacher assignment,
assessment status, record count, idempotency, and audit evidence once per
submission instead of emitting one event per score.

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

Future grading events must be compact facts and must not contain raw marks,
learner names, guardian data, private teacher notes, full reports, or raw grade
grids. Events should carry identifiers and counts only.

## Phase Boundaries

Compilation is separate from report generation. Phase 6B can add the full batch
submission service. Phase 6C can compile report-ready summaries. Report
generation, PDFs, parent delivery, and generated remarks remain later phases.

NLP or generated text must never decide grades. Human academic records remain
database-backed, auditable, tenant-scoped, and policy-controlled.
