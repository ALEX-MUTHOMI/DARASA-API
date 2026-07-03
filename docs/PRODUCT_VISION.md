# Darasa Product Vision: National-Scale, CBC-Native, Everyday School Software

This document exists so the scale target and the human target are explicit,
durable, and reviewable — not scattered across chat history. Architecture and
phase decisions in `docs/ARCHITECTURE_PHASES.md` and
`docs/PRODUCTION_READINESS_BACKLOG.md` should be read against this vision, not
against "one demo school."

## The Scale Target

Darasa is being engineered for **tens of thousands of Kenyan schools**, not
one pilot school. That target changes what "correct" means for almost every
design decision in this codebase:

- **Tenant isolation is not a nice-to-have.** With potentially 100,000+
  independent schools, a single cross-tenant data leak is not an edge case —
  it is a near-certainty at scale if isolation is enforced by convention
  (remembering to filter by `tenant_id`) instead of by structure. This is
  exactly why Darasa uses schema-per-tenant (`django-tenants`) rather than
  row-level multi-tenancy — see
  [ADR 0002](adr/0002-schema-per-tenant-isolation.md). At this scale,
  "usually filters correctly" is a production incident waiting to happen.
- **Uniform assumptions about school capacity are a design bug.** A 3,000-
  learner urban academy with dedicated IT staff and fibre, and a 120-learner
  rural school with one shared smartphone and intermittent connectivity, are
  both "a school" in Darasa's tenant model — but they cannot be assumed to
  have the same device access, bandwidth, staffing, or digital literacy.
  Every user-facing workflow (grading entry, evidence upload, notice
  delivery) must degrade gracefully for the low-capacity end of that range,
  not just work well in a demo on the high-capacity end. This is why the
  grading engine already treats offline-tolerant drafts, batch submission,
  and idempotent retries as first-class concerns (see
  `docs/GRADING_ENGINE.md`) rather than an afterthought bolted onto a
  connectivity-assumes-always-on design.
- **National rollout is a distinct engineering phase, not a bigger version of
  local rollout.** `docs/PRODUCTION_READINESS_BACKLOG.md` exists precisely
  because "works for one tenant in a demo" and "safe for 100,000 tenants"
  are different engineering problems: connection pooling, migration rollout
  time, notice-batch fan-out, and query patterns that scan "all schools" are
  all correctness bugs at national scale even when they are invisible at
  pilot scale.

## CBC Is a Moving Target, Not a Fixed Spec

Kenya's Competency-Based Curriculum is actively evolving — new subjects,
pathways, rubrics, and regulatory guidance are still being published and
revised as CBC matures and Senior School rolls out nationally. Software that
hard-codes "the current CBC structure" into its data model will be rebuilt
every time the curriculum changes. Darasa's answer to this is architectural,
not aspirational:

- The **curriculum graph** (`app/curriculum`) models CBC as versioned,
  navigable structure (strands, sub-strands, outcomes, competencies, rubric
  foundations) rather than as hard-coded constants, so a curriculum revision
  is a new version, not a schema migration.
- **CCT** (the Curriculum Change Tracker) exists specifically because CBC's
  pace of change is a first-class product requirement, not an edge case: it
  is Darasa's mechanism for absorbing new official guidance safely (evidence
  → verification → governance approval → publication → school adoption)
  without ever letting curriculum churn silently corrupt historical grading
  records. See [ADR 0003](adr/0003-evidence-based-cct-over-live-crawler.md)
  and `docs/CCT_SECURITY_MODEL.md`.
- School-level interpretation (CATs, internal exams, practicals, department
  grading bands) is deliberately kept as a separate, tenant-owned layer
  (`SchoolGradingSchema`, Phase 6E) precisely because CBC compliance is
  national, but how a school internally organizes its own assessment
  calendar is not — and both need to be true at once without either layer
  corrupting the other.

The practical implication for the roadmap: as CBC continues to add pathway
detail, new Senior School guidance, and revised rubrics, Darasa should be
absorbing that as **curriculum data flowing through CCT**, not as backend
code changes to grading/academics. If a CBC change ever requires touching
`app/grading` model code rather than publishing a new curriculum version
through CCT, that is a signal the curriculum/grading boundary has leaked and
needs to be revisited.

## The Human Target: An Everyday Tool, Not a Records System

Darasa is not primarily a database with an admin panel — it is meant to be
the tool a class teacher opens every day to run a lesson's assessment, the
tool a HOD opens to review a moderation queue, the tool a deputy opens to
check department readiness before end-of-term, and the tool a principal
opens to see whether the school is on track. Each of those is a different
job, not a different filter on the same screen. Concretely, this means:

- **Role-shaped views, not role-gated versions of the same view.** Phase 6C
  onward already establishes that teacher, HOD, deputy/head, and principal
  projections read the *same compiled facts* but are *shaped differently* —
  scope, level of detail, and executive framing differ by role (see
  `docs/GRADING_ENGINE.md`, Phase 6D/7A sections). Any future frontend or API
  layer should preserve that principle: one source of truth, many
  role-appropriate lenses — not one generic screen with permission checks
  bolted on.
- **The backend contract has to be good enough to make "everyday tool" UX
  possible.** A teacher who has to fight slow, chatty, N+1-query endpoints
  during a live lesson will not adopt the tool no matter how architecturally
  sound the backend is. Performance work already tracked in
  `docs/PRODUCTION_READINESS_BACKLOG.md` (`GRD-P1-003` large-roster
  profiling, `GRD-P1-006` teacher workload stress testing) is not abstract
  scale-proofing — it is a direct precondition for daily classroom
  usability.
- **There is currently almost no HTTP API surface** (see
  `docs/API_DOCUMENTATION.md`) — grading, curriculum, and academics are
  service-layer only. "Feels like an everyday tool" cannot happen until a
  real, ergonomic API contract exists for a frontend (web, and eventually
  lower-bandwidth-tolerant mobile) to build against. Introducing that HTTP
  layer is the single largest gap between "architecturally sound backend"
  and "software a teacher opens every morning," and should be treated as
  its own deliberately-scoped phase rather than an incidental side effect of
  other feature work.

## How To Use This Document

When scoping new work, ask:

1. **Does this assume one school, or does it hold at tens of thousands of
   tenants with wildly different capacity?** If it only works for a
   well-resourced pilot school, it is not done.
2. **Does this hard-code today's CBC structure, or does it flow through the
   curriculum graph / CCT?** If a future curriculum revision would require
   changing this code rather than publishing new curriculum data, reconsider
   the design.
3. **Does this serve a specific role's actual daily job, or is it a generic
   screen with a permission check?** Teachers, HODs, deputies, principals,
   and (eventually, fail-closed until guardian-link models exist) parents
   each have a distinct job to be done.

This vision does not change any currently-active phase boundary in
`docs/ARCHITECTURE_PHASES.md` — it explains *why* those boundaries were
drawn where they were, and should inform which future phase gets prioritized
next.
