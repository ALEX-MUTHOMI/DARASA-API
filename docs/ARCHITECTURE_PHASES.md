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

## Active Boundary Rules

The default test command runs Phase 1 through Phase 4C work and excludes future
phase markers, integration-heavy tests, and chaos tests.

The grading app remains quarantined until its own phase creates intentional
migrations and policy tests. It must not be added back to the active Django app
registry early.

CCT never fetches live government sites. It validates source metadata and stores
evidence so a future ingestion layer can be reviewed separately.

Principal acknowledgement is not activation. A school can acknowledge an update
without Darasa changing active curriculum records, schemes, assessment behavior,
or learner records.
