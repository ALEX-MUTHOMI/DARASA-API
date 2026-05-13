# Darasa-Core Security Model

Darasa-Core uses tenant-scoped RBAC plus ABAC checks.

RBAC answers which broad role a user has. ABAC answers whether that user can
act on a specific tenant, resource, assignment, or evidence record. Missing
tenant, missing actor, inactive actor, missing role, inactive role, unknown
action, or inactive tenant binding denies access.

## Tenant Isolation

Tenant isolation is the primary boundary. Selectors and policies must filter by
school tenant whenever they read school-owned data. A user with a role in one
school does not gain authority in another school.

## Academic Data

Learner records are sensitive. Academic policies require an active tenant role,
and teacher access depends on active cohort and learning-area assignments. A
teacher does not get broad learner access by being a teacher globally.

## Curriculum Governance

Curriculum records are not learner records, but curriculum governance still
affects school operations. Source registration, review, publication, principal
notification, and acknowledgement are separate operations. This prevents
mass-assignment shortcuts and preserves audit evidence.

## Secrets and PII

Production secrets must come from environment variables. Fernet configuration is
validated at startup so encrypted-field behavior cannot silently degrade.

Governance text rejects obvious learner-specific PII patterns. This keeps
curriculum updates, regulatory notices, evidence cards, and acknowledgement
notes from becoming accidental child-data stores.
