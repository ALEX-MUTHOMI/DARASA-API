# CCT National Coverage & Distribution Network (Phase 7B.1)

## Status

Planning document. No application code implements this yet. This records a
design that emerged from an architecture discussion and should be treated as
the reference point for that implementation, not a claim that it exists.

## The Problem, Restated Precisely

CCT (`app/curriculum`) exists to make Darasa aware that official CBC
curriculum or regulatory truth changed, without ever becoming a live
crawler — see [ADR 0003](adr/0003-evidence-based-cct-over-live-crawler.md).
Today, awareness depends entirely on a principal or academic head choosing
to upload a circular. That has a structural weakness: in Kenya, information
about curriculum changes, teacher retooling schedules, and national
co-curricular events (drama festivals, music festivals, exam calendars)
often travels through informal channels — WhatsApp groups, sub-county
office conversations — faster and more reliably than official government
websites, and a single busy or unaware principal is a single point of
failure for their school's curriculum awareness.

The goal of this plan is **not** to make CCT read the internet — that
would just replace one unreliable source (a slow government website) with
another (an unverified crawl target), and it would remove the human
governance gate that makes CCT trustworthy in the first place. The goal is
to make CCT **not depend on any single human**, by multiplying how evidence
can reach it and by making one school's diligence benefit every other
school in the same scope automatically.

## Architectural Principle (non-negotiable)

Every mechanism in this plan is a new **front door** onto the existing
`CurriculumEvidenceSubmission` quarantine → verification → governance →
publication → adoption pipeline. None of them creates a second truth path,
none of them fetches external content autonomously, and none of them lets
volume or speed substitute for governance approval. Where this plan
introduces a "confidence" or "corroboration" signal, that signal is
explicitly scoped to mean **"prioritize this for human review faster,"
never "approve this automatically."** This line must not move, even under
pressure to move faster at scale.

## Architecture Plan

### 1. Ingestion: more doors, same pipeline

| Channel | Status | Notes |
| --- | --- | --- |
| Web upload | Exists | Current only real ingestion path. |
| WhatsApp 1:1 DM with a single Darasa business number | New | A school forwards a circular image/PDF privately. Never a group — see "Why not a WhatsApp group" below. Lands in the same quarantine as a web upload. |
| SMS declaration / nudge-reply | New | For schools without smartphone/WhatsApp access, or for lightweight structured replies (e.g. replying a keyword to confirm training attendance). |
| County/sub-county liaison, trusted submitter role | New | A designated human (Darasa ops staff or an official county/sub-county education contact) submits through the identical pipeline, with elevated review priority — the backstop for "nobody at the school uploaded it." Still a human clicking submit; not a scraper. |

All four terminate in the same `CurriculumEvidenceSubmission` model with
the same quarantine/malware-scan/content-verification requirements already
scoped in `CCT-P0-001` through `CCT-P0-005`
(`docs/PRODUCTION_READINESS_BACKLOG.md`). A WhatsApp- or SMS-sourced
submission gets **no special trust** for arriving via a different channel.

### 2. Crowd corroboration: redundancy becomes coverage, not just deduplication

`build_evidence_fingerprint()` and `duplicate_cluster_id` already exist and
already cluster identical circulars submitted by *different, independent
tenants* by document identity (checksum + claimed authority/reference
numbers), not by submitter. This plan's change is operational, not
structural: **surface cluster size to reviewers as an explicit
prioritization signal** ("14 schools across Kiambu independently submitted
this — review first"). One diligent academic head in a sub-county already,
today, produces a cluster that covers their less-diligent neighbors; this
plan makes that fact visible and useful instead of incidental.

Guardrail: cluster size must never lower the bar for governance approval or
skip a review step. A large cluster answers "is this worth reviewing
urgently," never "is this true."

### 3. Fan-out to non-submitters (the direct answer to "what if nobody at my school uploads it")

Today, `build_notification_payload()` sends evidence-backed notices scoped
to the submitting context. This plan extends that: once a circular is
**governance-approved and published**, run the existing bounded
notice-batch mechanism (`notice_batch_planning.py`) against **every tenant
matching the verified scope** (`scope_estimator.py` already supports
`region`/`county`/`sub_county`/`pathway`), not only the school that
submitted it. A principal who never uploaded anything still receives
"A verified KICD circular affecting your pathway was published — review
it," with the full evidence trail attached. One school's action benefits
every school in scope, automatically, without any of them needing to have
uploaded anything themselves.

### 4. Teacher retooling signal (new, bottom-up — closes a real, confirmed gap)

`TeacherReadinessRequirement` already exists but is entirely **top-down**:
it only records "this circular implies retooling is required." There is no
existing bottom-up path for a teacher to report attendance or learning from
retooling. This plan adds one:

- A lightweight self-declaration ("I am attending training X on date Y"),
  low-trust until corroborated by others.
- A post-training structured nudge ("what changed in what you learned?"),
  captured as PII-minimized, aggregatable evidence — never as curriculum
  truth.
- The same corroboration-confidence pattern as document clustering, applied
  to people instead of documents: if many teachers across many schools
  report similar post-training content in the same window, that is a
  strong, early "go look for the real circular, urgently" signal — often
  faster than an official document arrives, because it travels through the
  same human networks the government's own website cannot compete with.

This must stay a prioritization signal only, for the same reason as
document clustering: teacher self-reports are informal and can be
inconsistent, and must never substitute for governance-approved evidence.

### 5. Scope widening: not just curriculum

`regulatory_notice_classifier.py` currently classifies only
curriculum/exam/teacher-training notices (TSC, KNEC, KICD categories). This
plan adds a parallel category family — `school_calendar_event` /
`co_curricular_notice` (drama festival, music festival, ball games,
term/holiday dates) — governed by the identical pipeline, with a
deliberately lighter review weight than a curriculum rubric change (a
festival date carries far less academic-integrity risk than a grading
rubric change).

### 6. Proactive nudges for known recurring events

A new, small "expected event calendar" concept (not a crawler — an internal
model of "this type of circular/event usually appears around week N of the
year, based on prior years' evidence records") drives proactive reminders
before/during the expected window ("Term 2 drama festival circulars are
usually out by now — have you seen one?"), escalating to the
county-liaison backstop (#1 above) if the window closes with nothing
submitted.

### 7. Coverage dashboard

Reusing the exact pattern already proven for grading readiness (Phase 6D):
a per-region/county view of which schools have engaged with CCT recently
versus which are silent. This gives Darasa's ops team (or a county
education partner) an actual worklist, and drives the rollout sequencing
in the execution plan below data-first rather than by fixed schedule.

## Messaging Infrastructure (shared, not CCT-specific)

Grounded in real Kenyan-market research, not assumption (see chat record;
figures current as of mid-2026):

- **Precedent**: Zeraki (50%+ of Kenyan high schools) and the broader
  African EdTech market are explicitly **SMS-first**, not app- or
  WhatsApp-first — SMS-centric models are the ones documented as having
  survived in this market. This plan corrects an earlier draft's
  WhatsApp-first lean accordingly: **SMS is the universal, guaranteed
  channel; WhatsApp is the rich-media enhancement layer on top of it**, not
  a replacement for it.
- **Vendor recommendation: Africa's Talking** for both SMS and WhatsApp
  (and USSD/Voice later if a feature-phone fallback beyond SMS is wanted).
  Kenya-founded, developer-API-first, CAK-approved Sender ID process
  already exists, single vendor/contract/compliance review for an
  MoE-scale procurement instead of two. Celcom Africa is a credible
  fallback/second-quote option.
- **Cost basis (published rates, not final quotes)**: SMS ≈ KES 0.25–0.60
  per message. WhatsApp **Utility**-category messages to Kenya numbers ≈
  **$0.0040/message (~KES 0.52)** per Meta's own rate card — cost-comparable
  to SMS for our actual use case, as long as every proactive message is
  classified as Utility, never Marketing. Estimated recurring cost at
  meaningful (not yet full national) scale: **order of magnitude KES
  150,000–400,000/month (~$1,150–$3,100/month)** — small relative to any
  credible MoE/donor EdTech budget line, but this is an estimate, not a
  vendor quote, and should be confirmed before being treated as a number.
- **Why this is shared infrastructure, not CCT plumbing**: the
  phone-number-to-tenant/user binding, Utility-template messaging account,
  and nudge-engine pattern built here are directly reusable by any future
  daily-engagement feature — most immediately, teacher attendance
  check-ins (see below). Building it as a general messaging platform now,
  rather than CCT-specific code, avoids rebuilding it later.

## Why Not A WhatsApp Group

WhatsApp Groups cap at ~1,024 members (cannot hold 100K principals
regardless of appetite) and make every member visible to every other member
— exactly the social friction a competitive, hierarchy-conscious set of
school leaders would resist. The correct primitives are directional:

- **Darasa → schools (distribution)**: a WhatsApp **Channel** — one-way
  broadcast, unlimited followers, followers invisible to each other.
- **Schools → Darasa (ingestion)**: **1:1 private chat** with a single
  Darasa WhatsApp Business number — every school talks privately to
  "Darasa," never to each other, scales to any number of schools.

No group is used at any point.

## Client/Human-Side Plan

| Stage | Plan |
| --- | --- |
| Onboarding | Self-service phone verification (OTP) where a school is ready; staged manual onboarding by region otherwise. Primary + backup contact per school — not just "the principal" — because staff turnover is real and must not silently break coverage. |
| Coaching | On-site/remote training, modeled on Zeraki's own explicitly-stated trust driver ("on-site training for teachers and administration"). A one-page "forward circulars to this number" workflow, not a manual. |
| Trust | Every notification already carries `NO_AUTO_MUTATION_NOTICE` ("Darasa has not automatically changed your school records. Principal review and school activation are required.") — this existing discipline is the direct counter to "yet another unreliable system" skepticism, and should be foregrounded in onboarding messaging, not buried in fine print. |
| Incentive | **Open, not decided.** A comparative/leaderboard framing risks the same competitive friction flagged for the WhatsApp-group idea. A private "your school's curriculum-awareness status" view is safer by default, but this needs real product testing with actual principals before committing. |
| Consent | Explicit opt-in capture at onboarding (required by Meta for template messages regardless), disclosed as part of the DPA compliance work already tracked in `docs/PRODUCTION_READINESS_BACKLOG.md` (`DAT-P0-001`/`002`). |
| Rollout | Pilot one county, fully — not a national big-bang. Use the coverage dashboard (#7 above) to decide the next county, data-first rather than on a fixed timeline. Recruit/define the county-liaison backstop role in parallel with the pilot, not after it. |

## Open Decisions (need explicit sign-off before implementation)

1. Africa's Talking vs. an alternative Kenya-based BSP — needs a real
   vendor quote, not the published rate card, before commitment.
2. Who plays the county/sub-county liaison role initially — Darasa's own
   team, or an existing relationship with specific education offices.
3. Incentive design for engagement (leaderboard vs. private status view vs.
   something else) — needs product validation with real principals.
4. Pilot county selection.
5. Consent-flow copy and legal review sign-off (ties to the broader DPA
   compliance backlog, not unique to this plan).

## Relationship To "Darasa Runs The Whole School Academic System"

CCT is one subsystem of that vision — the curriculum-truth-and-awareness
one — alongside tenant/identity, academics, and grading (already extensive
through Phase 7A). It is explicitly **not** a general school-management
replacement, and this plan does not expand its scope beyond curriculum and
school-calendar/co-curricular awareness.

**Teacher attendance does not exist in Darasa today.** It is a distinct,
currently-unbuilt module, tracked separately in
`docs/ROADMAP_TO_PRODUCTION.md` as a future phase — not part of CCT. The
architecturally significant point is that the messaging platform built for
this plan (phone-to-user binding, Utility-template infrastructure, the
nudge-engine pattern) is directly reusable for it: a teacher "reply
PRESENT" via SMS or a WhatsApp morning check-in nudge uses the exact same
plumbing as a CCT training-window nudge. This is the practical argument for
building the messaging layer as shared infrastructure now rather than
CCT-specific code that would need to be half-rebuilt later.

## Sequencing

This plan is **Phase 7B.1**, sequenced alongside Phase 7B (CCT production
upload infrastructure — private storage, malware scanning, content
verification) in `docs/ROADMAP_TO_PRODUCTION.md`. It depends on Phase 7B's
infrastructure (evidence still needs private storage and malware scanning
regardless of which channel it arrived through) but is a distinct
deliverable: 7B makes the upload pipeline production-safe; 7B.1 makes the
network of who can reach that pipeline, and who benefits from it, far
larger than "the one principal who happened to upload something."
