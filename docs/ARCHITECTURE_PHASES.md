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

Phase 6C adds deterministic compilation: submitted official `GradeRecord`s are
converted into canonical learner snapshots, assessment snapshots, cohort /
learning-area summaries, and role-aware backend projections. One academic truth
feeds teacher, HOD, deputy/head, principal, and future parent-safe views.
Reports, PDFs, parent portal UI, and NLP remain future phases.

CCT Fortification strengthens the existing Curriculum Change Tracker into the
curriculum control plane that later readiness dashboards and reports can depend
on. It adds tenant-specific school adoption, withdrawal, rollback planning,
bounded notice batches, and dependency guards for grading, compilation, and
future reporting. It does not rebuild CCT, crawl live sources, interpret
curriculum with AI, or change historical grading/compilation records.

CCT red-team verification attacks the fortified control plane with malicious
URLs, executable HTML metadata, UUID guessing, role escalation, mass assignment,
invalid lifecycle transitions, event payload injection, and workload
amplification simulations. The expected result is bounded, tenant-scoped,
reference-only governance behavior; production traffic protection still
requires infrastructure rate limits and monitoring.

CCT Full-Proofing adds the operational evidence layer without turning uploads
into curriculum truth. Principals, deputies, and school administrators submit
quarantined evidence metadata and private storage references. CCT fingerprints
and deduplicates evidence, records deterministic document verification reports,
tracks the 24-hour review SLA, estimates scope conservatively, plans app impact,
records rollback candidates, and requires governance approval before any
publication workflow can proceed. Published still does not mean globally
adopted, and rollout remains tenant-specific, scoped, batchable, and
non-mutating for historical grading and compilation records.

CCT production-readiness hardening keeps the upload path metadata-only while
making the production contract explicit. Evidence carries malware-scan and
content-verification readiness states, governance approval is blocked until
trusted infrastructure marks evidence clean and content-verified, and step-up
confirmation, rate limits, WAF/DDoS controls, private storage, worker retries,
dead-letter handling, and operational monitoring remain production deployment
requirements rather than hidden application shortcuts.

Phase 6D adds grading readiness dashboards and report-ready projections. It is
a backend readiness layer, not report generation. It consumes submitted grade
batches, compiled Phase 6C facts, teacher assignment context, and CCT adoption /
withdrawal / rollback / app-impact state to answer whether the school can
safely proceed toward reports. Teacher, HOD, deputy/head, principal, and future
parent-safe projections derive from the same academic truth and stay role
scoped. Future parent readiness remains fail-closed until approved release and
guardian-link models exist. Reports, PDFs, frontend dashboards, parent portal
UI, and NLP remain future phases.

The production-readiness backlog in `PRODUCTION_READINESS_BACKLOG.md` is the
canonical list of remaining platform, security, observability, operations, CCT,
grading, and governance work. CCT is application-architecture stable; CCT
public uploads and Darasa-Core as a whole are not production-ready yet.

## Active Boundary Rules

The default unit test command includes Phase 1 through Phase 6D work and
continues to exclude future markers, integration-heavy tests, and chaos tests.
Darasa also has explicit test gates: Patch/Turbo for fast feedback, Domain for
changed-domain verification, Full for phase closeout, and Deep for
security/red-team/performance sweeps. Patch/Turbo is not a merge or release
gate; Full remains the authoritative source of truth.

The grading app is intentionally active for Phase 6A and later. Future report,
scheme, lesson-assistant, external broker, crawler, and AI-parser work remains
inactive until its own phase creates intentional migrations, policies, and
tests.

CCT never fetches live government sites. It validates source metadata and stores
evidence so a future ingestion layer can be reviewed separately.

Principal acknowledgement is not activation. A school can acknowledge an update
without Darasa changing active curriculum records, schemes, assessment behavior,
or learner records.

Published curriculum is not school adoption. New grading assessments require a
published version that the tenant has explicitly adopted. Existing operational
assessments, submitted grades, and compiled snapshots preserve their original
curriculum context if CCT later publishes, withdraws, or rolls back a version.
Readiness projections may surface those CCT states as blockers or review flags,
but they do not silently rebind curriculum context or alter historical academic
records.
