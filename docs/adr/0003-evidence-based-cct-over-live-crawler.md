# ADR 0003: Evidence-based CCT instead of a live curriculum crawler

## Status

Accepted. Implemented across Phase 4A, 4C, CCT Fortification, Full-Proofing,
and production-readiness hardening (`app/curriculum`).

## Context

Kenya's CBC curriculum changes via official government/regulatory
publications. A tempting design is to have Darasa **crawl** government sites
directly, parse changes with some AI/NLP layer, and auto-publish updates so
schools always have "the latest curriculum" with zero manual effort.

That design has a serious failure mode for an academic-record system:
scraping and auto-interpreting official text is exactly the kind of
non-deterministic, unverified pipeline that must never be allowed to silently
rewrite what "curriculum truth" means for thousands of already-graded
learners.

## Decision

CCT never fetches live government sites and never auto-publishes. Instead:

- Principals, deputies, and school administrators submit **evidence**
  (metadata + a private storage reference to a document), not curriculum
  truth.
- Evidence is quarantined, fingerprinted (to deduplicate repeated uploads of
  the same circular into one review cluster), and scored by deterministic,
  reviewable signals (reference numbers, dates, authority claims, stamp/
  signature/template metadata) — never by an AI/NLP judgment call.
- A human governance decision (currently gated on the `school_admin`
  governance role, pending dedicated `curriculum_reviewer`/
  `curriculum_publisher` roles — `CCT-P0-006`) is required before any
  publication step, and publication itself is still separate from
  **school adoption**: a published version is not globally active until each
  tenant explicitly adopts it.

## Consequences

- Darasa can never be manipulated into "publishing" a fabricated regulatory
  notice purely by an attacker submitting a well-formed-looking upload —
  there is always a human decision point, and the confidence score is
  advisory only ("recommended next action," never "auto-approved").
- This intentionally trades away "curriculum updates itself automatically"
  for "curriculum updates are slower but auditable and cannot be silently
  wrong." For an academic-record system whose outputs (report cards,
  transcripts) have real consequences for children, this trade-off is
  treated as non-negotiable rather than a temporary MVP shortcut.
- It means the actual ingestion/crawling/AI-parsing layer this ADR
  deliberately excludes remains a distinct, separately-reviewed future
  system boundary (`docs/ARCHITECTURE_PHASES.md`: "CCT never fetches live
  government sites... so a future ingestion layer can be reviewed
  separately"), not a missing feature of the current CCT.
- Real production upload infrastructure (private object storage, malware
  scanning, content verification, step-up confirmation, rate limiting) is
  still required before this evidence-submission path can be exposed
  publicly — tracked as `CCT-P0-001` through `CCT-P0-005`.
