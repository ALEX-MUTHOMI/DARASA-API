# Roadmap To Production

This is the single, current answer to "what is left, and in what order." It
supersedes the stale "return to Phase 6D" pointer that used to live in
`docs/PRODUCTION_READINESS_BACKLOG.md` (Phase 6D, 6E, and 7A are all done).

Read this alongside three other documents rather than in isolation:

- `docs/PRODUCT_VISION.md` — *why* these phases are sequenced the way they
  are (national scale, CBC as a moving target, "everyday tool" usability bar).
- `docs/ARCHITECTURE_PHASES.md` — the full record of what has already been
  built, phase by phase.
- `docs/PRODUCTION_READINESS_BACKLOG.md` — the detailed, ID-tagged (`CCT-*`,
  `GRD-*`, `EVT-*`, `SEC-*`, `INF-*`, `OBS-*`, `TST-*`, `DAT-*`, `GOV-*`)
  backlog that each phase below draws its scope from. This document sequences
  that backlog; it does not replace it.

Per engineering policy, phases are scoped by **technical dependency and
invasiveness**, not calendar time. "What must be true before this can start"
and "how much of the codebase does this touch" are the right questions —
not "how many weeks."

## Where We Are Right Now

Phases 1 through 7A are complete (tenant identity, academics, curriculum/CCT,
event backbone, grading through report-snapshot/analytics foundation — see
`docs/ARCHITECTURE_PHASES.md`). On top of that, this session closed out a
cross-cutting hardening pass that several phases below assumed was still
open:

- **Application-layer observability** (structured logs, request
  correlation, Prometheus metrics, fail-closed metrics endpoint, live
  OpenAPI docs) — `docs/OBSERVABILITY.md`.
- **CI/CD pipeline hardening** against the OWASP CI/CD Top 10 (SHA-pinned
  Actions, digest-pinned Docker base image, real CODEOWNERS enforcement on
  pipeline paths, Dependabot) — `docs/security/OWASP_CICD_AUDIT_AND_INFRA_CHECKLIST.md`.
- **Dependency vulnerability remediation** (16 known CVEs across 5 packages,
  now zero) with a working, verified `poetry lock --regenerate` process.
- **Dynamic (DAST) baseline scanning** via OWASP ZAP, including fixing a
  structural blocker (no provisioned tenant meant every URL 404'd for any
  scanner) and real findings the first scan surfaced and this session fixed
  — `docs/security/ZAP_DAST_STRATEGY.md`.

None of that closes a specific numbered phase below, but it removes
foundational risk (dependency CVEs, pipeline supply-chain risk, zero
visibility into request health) that would otherwise have blocked several of
them.

## Phase Numbering Note

`docs/EVENT_BACKBONE.md` and `docs/GRADING_ENGINE.md` already reference
Phase 9 (safe NLP boundary), Phase 10 (API/Integration Contract Suite),
Phase 11 (observability/dashboard hooks), Phase 13 (WAF design), Phase 14
(performance baseline), and Phase 15 (production infrastructure) for
specific pieces of future work. This roadmap keeps those numbers and fills
in the previously-unnamed 7B, 8, and 12 consistently with them — it does not
renumber anything already referenced elsewhere in the docs.

## Phase 7B — CCT Production Upload Infrastructure

**Scope:** `CCT-P0-001` through `CCT-P0-008` in the backlog — private object
storage, a malware-scanning worker, a content-verification (MIME/type
sniffing) worker, step-up confirmation for evidence submission, upload rate
limiting, dedicated curriculum governance roles (replacing the current
temporary `school_admin` governance authority), production notice-delivery
workers, and CCT monitoring/alerting.

**Why now:** CCT's evidence-submission *application logic* is already fully
built, hardened, and red-team tested (Full-Proofing, production-readiness
hardening phases). The only thing standing between that and a real public
upload endpoint is infrastructure this backlog already itemizes precisely.
This is the most concretely scoped, lowest-ambiguity remaining P0 work.

**Dependencies:** None blocking. Can start immediately. Does not require the
Phase 10 API layer — CCT's HTTP-facing upload endpoint can be introduced as
part of this phase specifically, ahead of the broader API contract suite, or
folded into Phase 10 if sequencing favors building the API layer once.
**Decide this explicitly before starting** rather than accidentally building
two separate HTTP-endpoint efforts.

**Must not do:** Rebuild CCT's application logic, add AI/NLP curriculum
interpretation, or let infrastructure readiness imply governance-role
readiness (`CCT-P0-006` is a distinct, required deliverable, not a side
effect of storage/scanning existing).

## Phase 8 — Report Rendering and Delivery

**Scope:** `GRD-P0-002` (report readiness gates finalized), PDF/report-card
rendering from Phase 7A's frozen `LearnerReportSnapshot` /
`ReportSubjectLineSnapshot` / `AcademicAggregate` records, and role-scoped
delivery of rendered reports (teacher/HOD/deputy/principal views — parent
delivery stays fail-closed per `docs/GRADING_ENGINE.md` until guardian-link
models exist).

**Why now:** Phase 7A deliberately stopped at "frozen facts + aggregates,"
explicitly deferring rendering. Report rendering is the most-requested,
most-visible remaining grading feature and has no unresolved architectural
question left — it consumes an already-stable read model.

**Dependencies:** Phase 7A (done). Does not depend on Phase 7B or Phase 10.

**Must not do:** Mutate `GradeRecord`, compiled snapshots, or report
snapshots to produce a report; regenerate/recompute facts at render time
instead of reading the frozen snapshot; introduce NLP-generated narrative
text (that is Phase 9, and must ground itself in these same frozen facts,
not invent new ones).

## Phase 9 — Safe NLP Boundary

**Scope:** Rule-grounded, template-driven narrative remark generation
(`FAP-P3-002`), strictly from approved, report-ready `LearnerReportSnapshot`
facts. Cannot decide grades, curriculum truth, or corrections; output is
always a reviewable draft, never an auto-published final record.

**Dependencies:** Phase 8 (there must be an actual report to attach a
narrative remark to). `FAP-P3-002`'s grounding-boundary certification should
be written and reviewed *before* any generation code exists, not after.

**Sequencing note — read before scheduling this phase:** the existing
phase-number references treat 9 before 10, but `docs/PRODUCT_VISION.md`'s
priority (an everyday tool for teachers/principals) is better served by
Phase 10 (the API layer) landing first. Narrative remarks are a refinement
on top of reports that already have no way to reach a teacher's screen
without Phase 10 existing. **Recommendation:** build Phase 10 before Phase
9 in practice, even though Phase 9's number is lower; do not let the number
imply required build order.

## Phase 10 — API / Integration Contract Suite

**Scope:** The real HTTP API layer for grading, curriculum/CCT, academics,
and events — the single largest gap identified in `docs/PRODUCT_VISION.md`
and `docs/API_DOCUMENTATION.md`. Concretely: DRF serializers/viewsets over
the existing service layer (not a rewrite of that layer — it is already
tenant-scoped, ABAC-enforced, and tested), request/response versioning,
idempotency-key headers for at-least-once-safe client retries (referenced in
`docs/EVENT_BACKBONE.md`), pagination, and a consistent error-response
contract.

**Why this is the highest-leverage remaining phase:** almost everything else
on this roadmap either depends on it (frontend, mobile, CCT dynamic security
testing via ZAP, "everyday tool" usability) or is made meaningfully easier
by it (Phase 8 report delivery, Phase 9 remark delivery). It is also the
most architecturally invasive item remaining: it is a genuine new layer, not
an extension of an existing one, and needs its own design review before
implementation (request/response shape conventions, auth flow for the
existing JWT setup, per-role field visibility matching the "role-shaped
views, not role-gated views" principle in `docs/PRODUCT_VISION.md`).

**Dependencies:** None blocking structurally. Benefits from Phase 8 existing
(so report endpoints have something real to expose) but does not require it.

**Must not do:** Expose raw ORM shapes 1:1 as a shortcut; skip the
tenant/ABAC checks the service layer already enforces by calling models
directly from views; treat this as "just add DRF" without a deliberate
API-contract design pass first (see `TST-P1-007` permission matrix tests —
this phase should extend that matrix to cover every new endpoint).

## Phase 11 — Domain Observability Hooks and Frontend Groundwork

**Scope:** Domain-specific metrics beyond the HTTP-request-level metrics
already wired (grading batch submission latency, CCT evidence queue depth,
event dispatch backlog/age, compilation duration) per `OBS-P1-004`, plus
initial web-frontend scaffolding that consumes Phase 10's API contract for
the first real screen (recommend: the teacher grading grid from Phase 6B,
since its backend contract is already fully built and tested).

**Dependencies:** Phase 10 (API layer) for the frontend groundwork half;
domain metrics can start in parallel since they only need the service layer,
which already exists.

**Must not do:** Build a full frontend application in this phase — this is
explicitly "groundwork" (one real screen, proving the API contract works
end-to-end for a real workflow) before Phase 12 commits to a full client.

## Phase 12 — Frontend Web Client and Parent Portal Groundwork

**Scope:** A real web client covering the role-shaped views
`docs/PRODUCT_VISION.md` describes (teacher, HOD, deputy/head, principal),
built on Phase 10's contract and Phase 11's proof-of-concept screen. In
parallel: the guardian-link data model that every "parent/guardian" fail-closed
boundary in the grading/reporting domains has been deliberately waiting for
(`FAP-P3-001`).

**Dependencies:** Phase 10 (API), Phase 11 (groundwork).

**Must not do:** Activate parent-facing analytics or report delivery before
the guardian-link model and an explicit report-release approval step both
exist — every parent-facing fail-closed boundary in the codebase is
intentional, not an oversight to "just turn on" once a frontend exists.

## Phase 13 — Edge Security Design (WAF, Rate Limiting At Scale)

**Scope:** `SEC-P0-001` (WAF/DDoS), `SEC-P0-002` extended from today's
single-endpoint throttle to tenant-and-role-aware rate limiting across the
now-real API surface, `SEC-P1-005`/`SEC-P1-006` extended CSP/CSRF review for
a browser-facing frontend (cookies may enter the picture for the first time
depending on the frontend's auth strategy), and `SEC-P1-013` threat model
review — now meaningful, because Phase 10-12 finally created a real,
substantial attack surface to model.

**Dependencies:** Phase 10 (there must be a real API surface to design edge
protection around — designing this earlier would be premature/speculative).

**Must not do:** Treat this as "buy a WAF product and turn it on" without
first re-running `docs/security/ZAP_DAST_STRATEGY.md`'s dynamic scan against
the full Phase 10-12 surface (including CCT's new endpoints) to know what
edge rules actually matter.

## Phase 14 — Performance Baseline and National-Scale Proof

**Scope:** `TST-P1-002` through `TST-P1-004` (load tests, tenant-scale
tests, large-roster tests), `GRD-P1-003`/`GRD-P1-006` (large-roster
profiling, teacher workload stress testing — now against real HTTP traffic,
not just service-layer calls), `INF-P1-006` (read replicas), and the
external broker decision (`EVT-P1-003`) — Kafka/SQS/EventBridge/Kinesis,
justified by real traffic shape observed from Phase 11's domain metrics, not
guessed in advance.

**Dependencies:** Phase 10 (needs real HTTP traffic patterns to load-test
against) and Phase 11's domain metrics (needs a baseline to compare load
test results to).

**Must not do:** Introduce an external broker "because Kafka is standard" —
`docs/EVENT_BACKBONE.md` is explicit that this decision must be justified by
measured need, and the current outbox-based backbone (ADR 0001) already
supports migrating to one later without an architecture change.

## Phase 15 — Production Infrastructure and National Rollout

**Scope:** Everything in `docs/PRODUCTION_READINESS_BACKLOG.md` still tagged
P0/P1 that is infrastructure rather than application code: HA database +
backups/PITR (`INF-P0-001`/`002`), secrets manager (`INF-P0-005`/`SEC-P0-003`),
load balancer/TLS (`INF-P0-004`), autoscaling (`INF-P1-007`), WAF production
deployment (from Phase 13's design), Kubernetes or equivalent production
deployment topology, production dashboards/alerting/SLOs
(`OBS-P1-005`/`006`), disaster recovery (`INF-P1-012`), data retention/PIA
sign-off (`DAT-P0-001`/`002`, `DAT-P2-006`), and formal governance closeout
(`GOV-P0-002` branch protection, `GOV-P1-*` review checklists).

**Dependencies:** Every prior phase. This is deliberately the last phase —
it is where "does this work for one well-resourced pilot school" becomes
"does this work for tens of thousands of schools with wildly different
capacity," per `docs/PRODUCT_VISION.md`'s scale target.

**Definition of done:** `docs/PRODUCTION_READINESS_BACKLOG.md` section 14
("Definition of Production-Ready") already states this precisely and is not
duplicated here — that section is the actual exit criteria for this phase
and for the roadmap as a whole.

## Summary Table

| Phase | Name | Primary dependency |
| --- | --- | --- |
| 7B | CCT Production Upload Infrastructure | None — start now |
| 8 | Report Rendering and Delivery | Phase 7A (done) |
| 9 | Safe NLP Boundary | Phase 8; recommend building after Phase 10 in practice |
| 10 | API / Integration Contract Suite | None structurally — highest leverage, start early |
| 11 | Domain Observability Hooks + Frontend Groundwork | Phase 10 |
| 12 | Frontend Web Client + Parent Portal Groundwork | Phases 10, 11 |
| 13 | Edge Security Design (WAF, scaled rate limiting) | Phase 10 |
| 14 | Performance Baseline and National-Scale Proof | Phases 10, 11 |
| 15 | Production Infrastructure and National Rollout | All prior phases |

Phase 7B and Phase 10 have no blocking dependency on each other and can be
worked in either order or in parallel by separate efforts; every other phase
follows the dependency chain above.
