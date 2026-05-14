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

## Workflow Integrity

Detected changes cannot publish directly. A change must move through quarantine,
review, approval, publication, and later supersession. Rejected changes remain
auditable and cannot be published.

Curriculum versions are preserved instead of overwritten. Publications activate
reviewed versions, while notification evidence cards inform principals. A
principal acknowledgement records that the school has seen the evidence; it does
not activate curriculum or mutate school operations.

## Senior School Intelligence

Phase 4C focuses on Senior School impact and tracks Junior-to-Senior signals
only when they affect Senior School readiness, transition, pathways, assessment
guidance, or teacher readiness. It does not build a Junior School product layer.
