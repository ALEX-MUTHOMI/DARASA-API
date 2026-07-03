# Curriculum Change Tracker Security Model

CCT is Darasa's curriculum firewall and control tower. It records evidence about
official curriculum and regulatory changes without becoming a crawler or an
auto-publishing bot.

## Grading Boundary

CCT owns curriculum truth; grading owns assessment and academic records. An
operational grading assessment stores references to the approved curriculum
version, learning area, and rubric foundation. Grading validates that stored
context and then uses it for grade records.

CCT source validation, artifact quarantine, diffing, and regulatory
classification must not run per mark or per grade record. Later CCT
publications do not silently rebind old assessments; historical grade records
remain tied to the assessment context used when grading began.

Phase 6D grading readiness consumes CCT adoption, withdrawal, rollback, and app
impact facts as bounded blockers. It does not call CCT source validation, crawl
live sources, mutate CCT, or re-resolve curriculum truth per learner, mark, or
grade record. A CCT blocker may stop report readiness or require review, but it
does not mutate historical assessments, grade records, or compiled snapshots.

## Source Trust

Official authorities are allowlisted by code and domain. Source URLs must use
HTTPS, approved hosts, and the canonical HTTPS port. Credentialed URLs,
localhost, private IPs, metadata endpoints, and fake official-looking hosts are
rejected before any future fetch layer could use them.

## Artifact Quarantine

Source artifacts require bounded file size, allowed content type, safe file
name, and SHA-256 checksum. Artifacts start quarantined and cannot become
trusted automatically.

School-uploaded or manually submitted material is evidence, not curriculum
truth. Future upload endpoints must add a principal/deputy/head role gate,
step-up confirmation, file size limits, MIME and content verification,
checksum fingerprinting, malware-scan-ready private storage, no public direct
file URLs, no macro execution, no unsafe parsing in the request path, rate
limits, and audit logs.

Evidence metadata and governance notes are stored as untrusted plaintext. The
backend rejects executable HTML patterns and obvious learner PII; any frontend
or future document renderer must still escape output and must not render raw
circular text as trusted HTML.

## Evidence Upload Full-Proofing

Principals, deputies, and school administrators may submit evidence metadata
and private storage references. They submit evidence, not curriculum truth.
Every `CurriculumEvidenceSubmission` starts quarantined, is tenant-owned, and
stores checksum, fingerprint, submitter role, claimed authority, claimed
reference numbers, publication/effective dates, and claimed scope. Client
payloads cannot set reviewer, publisher, publication, adoption, or trusted
status fields.

Evidence fingerprints are based on document identity and checksum, not private
storage location. This lets Darasa attach repeated uploads of the same circular
to one duplicate cluster instead of creating thousands of review cases. A
cross-tenant duplicate may share a cluster identifier, but it does not expose a
foreign tenant's evidence row through a direct `duplicate_of` relationship.

Private storage references are metadata only. CCT does not fetch submitted
URLs or parse uploaded files in the request path. Production upload endpoints
must add step-up confirmation, request rate limits, file size limits, MIME and
content sniffing, extension allowlists, malware-scan-ready private storage, no
public direct file URLs, no macro execution, no archive extraction, and audit
logging of uploader, tenant, session/IP, and timestamp.

Each evidence submission carries upload-readiness statuses. Malware scan status
is `pending`, `clean`, `suspicious`, `infected`, or `unavailable`; content
verification status is `pending`, `passed`, `failed`, or `unsupported`.
Production scanners and content-sniffing workers will set those statuses from
trusted infrastructure only. Client payloads cannot mark evidence clean or
verified. Governance approval for publication requires `clean` malware status
and `passed` content verification; pending, suspicious, infected, unavailable,
failed, or unsupported evidence can remain under review but cannot advance to
publication approval.

Document verification reports record deterministic signals: reference number,
publication number, dates, stamp/signature/template metadata, authority status,
duplicate signal count, scope guess, risk flags, missing evidence, confidence
score, confidence level, recommended next action, and a 24-hour SLA due time.
These are evidence signals only. High confidence and a 24-hour SLA never
auto-approve, auto-publish, or auto-adopt a curriculum update.

Governance approval is a separate decision. Current backend governance approval
requires the school-admin governance role until dedicated curriculum reviewer
and publisher roles are modeled. Principals and deputies can submit evidence
but cannot approve publication through the full-proofing governance workflow.

## Workflow Integrity

Detected changes cannot publish directly. A change must move through quarantine,
review, approval, publication, and later supersession. Rejected changes remain
auditable and cannot be published.

Curriculum versions are preserved instead of overwritten. Publications activate
reviewed versions, while notification evidence cards inform principals. A
principal acknowledgement records that the school has seen the evidence; it does
not activate curriculum or mutate school operations.

## National Control Plane Fortification

CCT is Darasa's curriculum control plane for dependent apps. Detected evidence,
verified change sets, national publication, and school adoption are separate
states. A published version is not globally active for every school; each tenant
gets an explicit `SchoolCurriculumAdoption` record before new operational
assessments may bind to that version.

Withdrawals and rollback plans are auditable control-plane records. They block
new adoption or new grading bindings, but they do not rewrite old assessments,
grade records, compilation runs, compiled learner snapshots, or cohort
summaries. Historical academic facts keep the CBE/CCT context that governed the
assessment when grading began.

Principal evidence notices and teacher readiness notices remain evidence-backed
and tenant or assignment scoped. National-scale rollout must use bounded notice
batches rather than synchronous fan-out to every school.

Scope defaults to `scope_unknown`. A circular may be national, regional,
county, pathway, grade, learning-area, topic, rubric, or exam-cycle scoped; CCT
does not assume national impact. App impact plans are review facts for
academics, assessments, examinations, grading, compilation, future reports,
future schemes, teacher readiness, principal notices, parent analytics, and
future NLP. They do not mutate those apps.

Rollback and withdrawal candidates begin as quarantined evidence. Verified
withdrawals block future adoption and new grading bindings, but rollback plans
record intent only. They do not mutate `Assessment`, `GradeSubmissionBatch`,
`GradeRecord`, `CompilationRun`, compiled learner snapshots, or cohort
summaries.

Production DDoS resistance also requires infrastructure controls such as WAF,
rate limiting, request size limits, queue back-pressure, and operational
monitoring. The application layer only enforces bounded planning and scoped
selectors; it must not synchronously process every school, learner, document
page, or dependent app in one request.

Evidence submission is a production step-up action. Before live binary uploads,
the step-up confirmation must match the actor and tenant, must expire, and must
not store raw passwords, PINs, or recovery secrets. Current backend tests cover
metadata-only submission; production rollout must attach the real identity
confirmation mechanism before exposing upload endpoints.

Notice delivery remains a worker contract, not a request-path fan-out. Notice
batches must be resumable and idempotent, worker retries must be bounded, and
failed delivery must not roll back curriculum truth. Delivery facts and retry
events must remain reference-only.

Production monitoring must track evidence submissions per tenant, duplicate
cluster growth, verification SLA breaches, pending governance decisions,
rejected evidence, rollback candidates, withdrawn versions, pending or failed
notice batches, event dispatch failures, rate-limit violations, malware scan
failures, and content-verification failures.

`PRODUCTION_READINESS_BACKLOG.md` records the CCT blockers that remain before
public uploads can be exposed: private object storage, scanner workers,
content-verification workers, step-up confirmation, upload rate limits,
dedicated curriculum governance roles, notice delivery workers, and CCT
monitoring. These are production deployment blockers, not hidden features in
the current application layer.

## Senior School Intelligence

Phase 4C focuses on Senior School impact and tracks Junior-to-Senior signals
only when they affect Senior School readiness, transition, pathways, assessment
guidance, or teacher readiness. It does not build a Junior School product layer.

## Dynamic Security Testing

CCT has no HTTP endpoints today (see `docs/API_DOCUMENTATION.md`), so
dynamic scanners like OWASP ZAP have nothing CCT-specific to attack yet —
this is unrelated to CCT's own no-crawling rule above ("CCT is not a
crawler" describes Darasa's outbound requests; ZAP tests Darasa's inbound
HTTP surface, which are two different meanings of "crawl"). See
`docs/security/ZAP_DAST_STRATEGY.md` for the dynamic testing plan for once
Phase 10 exposes CCT's evidence-submission and governance endpoints over
HTTP, and for the real, verified fixes that strategy already produced
against the current minimal application-wide HTTP surface.
