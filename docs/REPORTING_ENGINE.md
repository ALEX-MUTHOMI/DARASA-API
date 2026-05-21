# Darasa-Core Reporting Engine

Phase 7A is the report snapshot and academic analytics foundation. It is not a
report renderer.

The reporting flow is:

```text
Grade Records
    -> Compilation Engine
    -> Readiness Checks
    -> Corrections / Moderation / Approval
    -> Report-Ready Snapshot
    -> Role-Specific Academic Analytics
    -> Report Generator later
    -> PDF / Parent Portal / NLP later
```

Reports and analytics must not read unstable live `GradeRecord` rows in
dashboard request paths. Phase 7A creates derived, tenant-scoped,
report-period-scoped read models:

- `ReportSnapshotRun`
- `ReportEligibilityRecord`
- `LearnerReportSnapshot`
- `ReportSubjectLineSnapshot`
- `AcademicAggregate`

Snapshots preserve source compilation references, readiness status,
correction-audit state, academic year, term, assessment context, CBE/CCT
curriculum version, rubric foundation, and school internal grading schema
version. CCT changes and school schema changes do not silently mutate existing
snapshots.

Eligibility fails closed when compilation is missing, failed, stale, or
blocked; readiness is not cleared; required components are missing; corrections
are pending or approved but unapplied; CCT withdrawal/rollback/app-impact
review blocks report use; or a required school schema is missing/deprecated.

Analytics are precomputed from report snapshots and aggregate read models for
school, cohort, stream, subject, and department scopes. Principal and deputy
views consume tenant executive/operations projections. HOD views are
learning-area scoped. Class-teacher views are cohort scoped. Subject-teacher
views are assignment scoped. Future parent analytics fails closed until
guardian-link and approved release models exist.

For national scale, dashboards must use bounded tenant/report-period selectors
and aggregate rows instead of scanning all schools, all learners, or raw grade
records. Aggregates carry a minimum-group-size flag so future portals can
suppress tiny-group analytics that could reveal individual learner performance.

Phase 7A intentionally does not implement PDFs, print templates, school-branded
report cards, final report text, NLP remarks, frontend screens, public APIs,
parent portal delivery, SMS/email delivery, external brokers, finance, crawler,
AI parser, or CCT upload infrastructure.
