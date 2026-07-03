# ADR 0005: Liveness checks bypass tenant resolution entirely

## Status

Accepted. Implemented via `core.middleware.HealthCheckBypassMiddleware`,
placed before `django_tenants.middleware.main.TenantMainMiddleware`.

## Context

Darasa resolves the active tenant schema per request by matching the Host
header against the `Domain` table (see
[ADR 0002](0002-schema-per-tenant-isolation.md)). A Host with no matching
tenant domain 404s by design — that is the correct behavior for real
application traffic.

Container orchestrators (Docker `HEALTHCHECK`, Kubernetes liveness/readiness
probes) and external uptime monitors are not "real application traffic" in
this sense: they have no reason to know, and generally cannot be configured
to send, any specific school's tenant domain as the Host header. They
typically probe by container IP or `localhost`. Before this change,
`/api/health/` behaved identically to every other route — it also 404'd for
any Host without a matching tenant domain — which means it 404'd for
*every* orchestrator health probe and uptime monitor in practice, the exact
callers a liveness endpoint exists to serve. This was found and confirmed
with a real running server, not assumed: `curl -H "Host: localhost"
.../api/health/` returned 404 against an unpatched checkout.

## Decision

`HealthCheckBypassMiddleware` intercepts the literal `/api/health/` path and
answers it directly, before any other middleware — including tenant
resolution — runs. It performs no database query and depends on nothing
tenant-specific, by design: a liveness check that itself depends on
per-tenant state is not answering "is the process alive," it is answering a
different, more complicated question.

## Consequences

- Docker's `HEALTHCHECK` directive (`Dockerfile`) and any future
  Kubernetes liveness/readiness probe configuration can now rely on
  `/api/health/` working regardless of how the probe addresses the
  container. Verified with a real `docker build` + `docker run`: `docker ps`
  reports the container `(healthy)`.
- This intentionally answers only "is the process alive," not "is this
  specific tenant's data reachable" or "is the database up." A deeper
  readiness check (e.g. verifying database/cache connectivity) would need
  its own endpoint and its own decision about whether that check should be
  tenant-aware — this ADR does not extend to that future endpoint.
- Any future endpoint added to this bypass list must be held to the same
  standard: no tenant-specific data, no side effects, safe to expose without
  the normal tenant-isolation guarantee, because it deliberately runs before
  that guarantee is established for the request.
