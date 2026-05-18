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

## Senior School Intelligence

Phase 4C focuses on Senior School impact and tracks Junior-to-Senior signals
only when they affect Senior School readiness, transition, pathways, assessment
guidance, or teacher readiness. It does not build a Junior School product layer.
