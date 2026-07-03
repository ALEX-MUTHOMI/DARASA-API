# ADR 0002: Schema-per-tenant isolation via django-tenants

## Status

Accepted. Implemented in Phase 2 (`app/tenant`, `django_tenants` in
`INSTALLED_APPS`/`MIDDLEWARE`).

## Context

Darasa serves many independent schools from one deployment. Two realistic
isolation strategies exist:

1. **Row-level multi-tenancy**: one shared schema, every table carries a
   `tenant_id` column, every query must filter by it.
2. **Schema-per-tenant**: one Postgres schema per school; the same table
   names exist once per schema; `django-tenants` switches the active schema
   per request based on the resolved tenant domain.

## Decision

Use schema-per-tenant (`django-tenants`), with `TenantMainMiddleware`
resolving the tenant from the request's `Domain` before any view or ORM call
runs.

## Consequences

- **A forgotten `tenant_id` filter cannot leak cross-tenant data** the way it
  can under row-level multi-tenancy — the query physically cannot see another
  schema's rows within the same connection/search_path. This is the
  strongest structural defense against the single most common multi-tenant
  SaaS bug class (IDOR/cross-tenant data leakage), at the cost of needing
  `django-tenants`-aware migration and connection handling.
- Shared, cross-tenant models (e.g. `School`, `Domain`, curriculum/CCT
  national-truth tables) must live in `SHARED_APPS` and the `public` schema,
  while tenant-owned operational data (grading, disciplinary, portals) lives
  in `TENANT_APPS`. Getting an app's placement wrong is a real failure mode
  this ADR flags explicitly for reviewers.
- Per-schema migrations mean schema count is a real operational scaling
  factor at national scale (thousands of schools): connection pooling,
  migration rollout time, and backup/restore strategy must all account for
  "many schemas," not "one schema with more rows." This is why
  `INF-P1-006`/`INF-P1-007` (read replicas, autoscaling) and
  `TST-P1-003` (tenant-scale tests) remain open production-readiness items.
- Local development and tests must always resolve a tenant domain before
  hitting any URL through the full middleware stack; there is currently no
  seeded "public/testserver" `Domain` fixture in the test suite, so existing
  tests exercise views directly via `APIRequestFactory` rather than through
  `reverse()`/`Client`. Adding that fixture is a prerequisite for any future
  true end-to-end HTTP test.
