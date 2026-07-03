# Darasa-Core

Darasa-Core is the backend for a multi-tenant academic ERP for Kenyan schools,
built around the Competency-Based Curriculum (CBC). It is an event-driven
Django modular monolith whose primary engineering focus is **academic-record
integrity and curriculum governance**, not CRUD: grade records, curriculum
truth, and report snapshots are treated as auditable facts that must never be
silently rewritten, even as curriculum, schemas, and correction workflows
change underneath them.

This README is written to be accurate, not aspirational. Where the project
still has real gaps, they are stated plainly below and tracked in
[`docs/PRODUCTION_READINESS_BACKLOG.md`](docs/PRODUCTION_READINESS_BACKLOG.md).

## Why This Is Harder Than It Looks

Most student/portfolio ERPs stop at "CRUD + JWT + Docker." Darasa-Core is
built around three problems that don't show up until a system has to survive
contact with real curriculum change, real teachers, and real audits:

1. **Curriculum governance as a first-class domain (CCT).** Official CBC
   updates are treated as *untrusted evidence* that must be quarantined,
   fingerprinted, deduplicated, human-reviewed, published, and then
   explicitly *adopted per school* before it can affect grading. Nothing
   auto-publishes; nothing silently rewrites history. See
   [`docs/CCT_SECURITY_MODEL.md`](docs/CCT_SECURITY_MODEL.md) and
   [ADR 0003](docs/adr/0003-evidence-based-cct-over-live-crawler.md).
2. **Grading as an auditable pipeline, not a form.**
   `Assessment → GradeSubmissionBatch → GradeRecord → Correction →
   Compilation → Readiness → Report Snapshot → Analytics`, where every stage
   is deterministic, idempotent, tenant/ABAC-scoped, and preserves the
   curriculum context that existed *when grading began* — even after later
   curriculum republishing, rollback, or school-schema changes. See
   [`docs/GRADING_ENGINE.md`](docs/GRADING_ENGINE.md).
3. **A local-first, broker-ready event backbone**, built on a transactional
   outbox (event and domain write commit atomically) rather than a
   dual-write, before any external broker exists to plug in. See
   [ADR 0001](docs/adr/0001-transactional-outbox-over-dual-write.md) and
   [`docs/EVENT_BACKBONE.md`](docs/EVENT_BACKBONE.md).

## Architecture At A Glance

```text
Request
  │
  ▼
TenantMainMiddleware          schema-per-tenant resolution; a forgotten
  │                           tenant filter physically cannot leak
  │                           cross-school data (ADR 0002)
  ▼
RequestObservabilityMiddleware   request id + structured logs + Prometheus
  │                              metrics bound for the request lifetime
  ▼
Django / DRF view  →  per-domain service layer
                            │
        ┌──────────┬────────┼──────────┬───────────┐
        ▼          ▼        ▼          ▼           ▼
     tenant      core    academics  curriculum   grading
   (schools,   (identity, (years,   (CBC graph,  (assessments,
    domains,    RBAC/ABAC) cohorts,  CCT evidence batches, grade
    roles)                 enrollments) governance) records, reports)
        │          │        │          │           │
        └──────────┴───┬────┴──────────┴───────────┘
                        ▼
        Domain write + Outbox row committed in one
        Postgres transaction, never a dual-write (ADR 0001)
                        │
                        ▼
        events/ dispatcher → in-process consumers
        (typed, versioned, idempotent, dead-letter-tracked;
         external broker adapter is a deliberately deferred,
         later phase — see docs/EVENT_BACKBONE.md)
```

Cross-domain database joins are forbidden by design (DDD boundary); domains
only communicate through service-layer calls within a request or through
outbox events across a transaction boundary. The system's internal name for
this shape is "The Citadel" (see `BLUEPRINT/`).

## Current Status (Phase 7A)

| Layer | Status |
| --- | --- |
| Tenant identity & RBAC/ABAC (`tenant`, `core`) | ✅ Implemented, tested |
| Academic core: years, terms, cohorts, enrollments (`academics`) | ✅ Implemented, tested |
| Curriculum graph + CCT governance (`curriculum`) | ✅ Implemented, hardened, red-team tested |
| Event backbone: outbox, idempotency, dead-letters (`events`) | ✅ Implemented, tested; **no external broker wired** |
| Grading: assessments → batches → corrections → compilation → readiness (`grading`) | ✅ Implemented through Phase 7A (report snapshots + analytics foundation) |
| **HTTP API surface** | ⚠️ **Minimal.** Only a health check, a stub parent-login endpoint, a Prometheus metrics endpoint, and live OpenAPI docs exist. Grading, curriculum/CCT, academics, and events are service-layer only — see [`docs/API_DOCUMENTATION.md`](docs/API_DOCUMENTATION.md). |
| Observability | ✅ Structured logging, request correlation, and HTTP metrics are wired and real (not just declared dependencies). Tracing is implemented but disabled until a collector is configured. See [`docs/OBSERVABILITY.md`](docs/OBSERVABILITY.md). |
| Report rendering, PDFs, parent portal UI, NLP, finance | ❌ Not started — explicitly out of scope until their own phase |
| Production infrastructure (object storage, malware scanning, WAF, HA DB, dashboards) | ❌ Tracked, not built — see the backlog below |

Full phase-by-phase history: [`docs/ARCHITECTURE_PHASES.md`](docs/ARCHITECTURE_PHASES.md).

## Engineering Discipline Worth Noting

- **Phase discipline with committed boundaries.** Every phase doc states what
  it explicitly does *not* do (e.g. "Phase 6C does not compile reports,"
  "CCT never fetches live government sites"). Scope is closed on purpose, not
  left open by omission.
- **Fail-closed by default.** Parent/guardian analytics fail closed until a
  real guardian-link model exists. ABAC checks fail closed on missing
  tenant/assignment context. An unconfigured metrics token means "closed,"
  not "open." Unknown CCT scope blocks automatic national rollout.
- **Historical immutability.** Corrections, curriculum republishing, and
  schema changes are designed to *supersede*, never mutate, past academic
  records or compiled snapshots.
- **Deterministic algorithm packages.** Security- and correctness-critical
  logic (`app/curriculum/algorithms/`, `app/events/algorithms/`,
  `app/grading/algorithms/`) is pure, side-effect-free, and independently
  unit-tested — services delegate to it rather than reimplementing rules
  inline.
- **A self-aware production backlog**, not a false "done" claim: see
  [`docs/PRODUCTION_READINESS_BACKLOG.md`](docs/PRODUCTION_READINESS_BACKLOG.md)
  for the prioritized (P0/P1/P2) list of what stands between this codebase
  and national-scale production rollout.

## By The Numbers

These are measured, not estimated — run locally against a real PostgreSQL 16
+ Redis 7 stack (no Docker required for this check; see
[`docs/DEVELOPER_ENVIRONMENT.md`](docs/DEVELOPER_ENVIRONMENT.md)):

- ~20,000 lines of application code (excluding migrations/tests).
- 21 migrations across 8 active Django apps.
- **354 tests** collected under the default (non-chaos, non-integration,
  non-`future`, non-`slow`) gate — **all 354 pass** against a real
  PostgreSQL 16 + Redis 7 stack and the Python 3.11.15 interpreter this
  repo's CI uses.
- `flake8` and Bandit run fully clean. `pip-audit` reports **zero known
  vulnerabilities with zero ignored advisories** (as of 2026-07-03) — a
  16-vulnerability, 5-package finding (cryptography, django, pyjwt, msgpack,
  pip) was found and fixed via `poetry lock --regenerate`, not silently
  ignored; see
  [`docs/PRODUCTION_READINESS_BACKLOG.md`](docs/PRODUCTION_READINESS_BACKLOG.md#7-security-and-compliance-backlog)
  for the dated record.
- The GitHub Actions pipeline itself is hardened against the
  [OWASP CI/CD Top 10](https://owasp.org/www-project-top-10-ci-cd-security-risks/):
  every third-party Action is pinned to a verified commit SHA, the
  production Docker base image is pinned by digest (not just tag), and
  CODEOWNERS enforces real review on every pipeline-execution-critical path.
  See [`docs/security/OWASP_CICD_AUDIT_AND_INFRA_CHECKLIST.md`](docs/security/OWASP_CICD_AUDIT_AND_INFRA_CHECKLIST.md).
- Layered test gates — Patch/Turbo, Domain, Full, Deep — tune local feedback
  speed and merge confidence independently
  (see [`docs/TESTING_STRATEGY.md`](docs/TESTING_STRATEGY.md)).
- Toxiproxy-based chaos tests (opt-in) inject latency/packet loss against the
  test database connection in CI.

## Local Commands

```bash
make build
make django-check
make lint
make security
make test
```

Chaos tests are opt-in:

```bash
make test-chaos
```

## Developer Environment

Darasa-Core is Docker-first and Poetry-compatible. CI is the source of truth for
quality gates; VS Code should use either the Poetry virtual environment or the
Docker Compose commands above. See [`docs/DEVELOPER_ENVIRONMENT.md`](docs/DEVELOPER_ENVIRONMENT.md)
for Pylance, Pylint, and interpreter setup guidance.

## Runtime Layout

- Django project: `app/darasa_project`
- Django entrypoint: `app/manage.py`
- Production image workdir: `/app`
- Production image scripts: `/scripts`
- Docker Compose development workspace: `/workspace`
- Docker Compose development scripts: `/workspace/scripts`

The production image copies `app/` to `/app` and `scripts/` to `/scripts`.
The development Compose stack bind-mounts the repository root at `/workspace`
so Poetry can see `pyproject.toml`, `.flake8`, and `poetry.lock` without nested
file mounts inside `/app`. Django commands should run from `/workspace/app`
when using Compose.

## Documentation Map

| Doc | What it covers |
| --- | --- |
| [`docs/PRODUCT_VISION.md`](docs/PRODUCT_VISION.md) | The national-scale, CBC-native, "everyday tool" product target that architecture decisions are made against |
| [`docs/ARCHITECTURE_PHASES.md`](docs/ARCHITECTURE_PHASES.md) | Full phase-by-phase build history and active boundary rules |
| [`docs/API_DOCUMENTATION.md`](docs/API_DOCUMENTATION.md) | The real (small) HTTP surface, honestly scoped |
| [`docs/OBSERVABILITY.md`](docs/OBSERVABILITY.md) | Structured logging, metrics, tracing — what's wired vs. backlog |
| [`docs/GRADING_ENGINE.md`](docs/GRADING_ENGINE.md) | The grading/compilation/readiness/report pipeline |
| [`docs/CCT_SECURITY_MODEL.md`](docs/CCT_SECURITY_MODEL.md) / [`docs/SECURITY_MODEL.md`](docs/SECURITY_MODEL.md) | Curriculum governance and platform security posture |
| [`docs/EVENT_BACKBONE.md`](docs/EVENT_BACKBONE.md) / [`docs/EVENT_ALGORITHMS.md`](docs/EVENT_ALGORITHMS.md) | Outbox, idempotency, dead-letter, and retry rules |
| [`docs/TESTING_STRATEGY.md`](docs/TESTING_STRATEGY.md) | Patch/Domain/Full/Deep gates and pytest markers |
| [`docs/PRODUCTION_READINESS_BACKLOG.md`](docs/PRODUCTION_READINESS_BACKLOG.md) | Prioritized list of what remains before production rollout |
| [`docs/security/OWASP_CICD_AUDIT_AND_INFRA_CHECKLIST.md`](docs/security/OWASP_CICD_AUDIT_AND_INFRA_CHECKLIST.md) | OWASP CI/CD Top 10 audit of the GitHub Actions pipeline itself |
| [`docs/adr/`](docs/adr/) | Architecture Decision Records for key trade-offs |

## Boundary

Darasa-Core handles academic ERP foundations only. Non-academic commercial
workflows (finance, admissions marketing, etc.) are intentionally outside
this repository.
