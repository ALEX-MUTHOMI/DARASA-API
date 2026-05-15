# Darasa-Core Architecture Phases

Darasa-Core is being built as a phased multi-tenant academic ERP. Each phase
adds one architectural layer and keeps future layers inactive until their
migrations, policies, and tests are intentional.

## Completed Foundations

Phase 1 established the Docker, Poetry, CI, lint, security, smoke-test, and
test-marker foundation.

Phase 2 added tenant identity: `School`, `Domain`, `CustomUser`, `Role`, and
tenant-scoped `TenantUserRole`. A role only grants access inside a specific
school tenant.

Phase 3 added the academic core: academic years, terms, grade levels, learning
areas, cohorts, learners, enrollments, teacher assignments, and assignment-aware
academic ABAC.

Phase 4 added the curriculum graph: source documents, curriculum versions,
grade mappings, learning-area mappings, strands, sub-strands, outcomes,
competencies, values, PCIs, and rubric foundations.

Phase 4A added CCT, the Curriculum Change Tracker. CCT is a governance firewall:
it validates official-source metadata, quarantines artifacts, fingerprints
sources, records change sets, and requires review before publication.

Phase 4C added Senior School regulatory intelligence: curriculum diffs,
regulatory notices, teacher-readiness requirements, impact records, and
principal evidence cards.

Phase 5 adds the event backbone: typed event contracts, a transactional outbox,
dispatch attempts, consumer idempotency state, dead-letter records, and audit
events. It is local-first and broker-ready, but it does not add an external
broker adapter.

Phase 5B hardens the backbone with deterministic algorithms for contract
validation, producer authorization, payload safety, idempotency, retry/backoff,
dead-letter classification, priority ordering, partition keys, audit hashing,
and dispatch batch planning. See `EVENT_ALGORITHMS.md`.

Phase 6A activates the grading core foundation: assessments, submission batch
boundaries, grade records, correction requests, tenant-aware selectors, ABAC
policies, and deterministic grading helpers. Reports, PDFs, generated remarks,
and parent-facing delivery remain future phases.

Phase 6A.1 binds operational assessments to CBE/CCT curriculum truth. CCT owns
official source governance and publication; grading stores the approved
curriculum/rubric context on the assessment and preserves that historical
context after grading begins. Teacher grade-entry paths expose only assigned,
open, bound assessments.

Phase 6B adds the backend teacher grading workflow: assigned work list,
spreadsheet grid contract, draft save/resume, practical/component grid support,
step-up-confirmed final submission, transactional grade-record commits, and one
compact batch-level event. It still does not compile report summaries.

## Active Boundary Rules

The default test command now includes Phase 1 through Phase 6B work and
continues to exclude future markers, integration-heavy tests, and chaos tests.

The grading app is intentionally active for Phase 6A and later. Future report,
scheme, lesson-assistant, external broker, crawler, and AI-parser work remains
inactive until its own phase creates intentional migrations, policies, and
tests.

CCT never fetches live government sites. It validates source metadata and stores
evidence so a future ingestion layer can be reviewed separately.

Principal acknowledgement is not activation. A school can acknowledge an update
without Darasa changing active curriculum records, schemes, assessment behavior,
or learner records.
