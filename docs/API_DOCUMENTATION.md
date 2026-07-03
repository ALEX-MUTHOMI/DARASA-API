# Darasa-Core API Documentation

## Real Status (updated post-Phase 7A)

This is deliberately honest, not aspirational: as of Phase 7A, **grading,
curriculum/CCT, academics, and the event backbone have no HTTP API surface at
all.** Those domains are fully built as service-layer Python (`services.py`,
`selectors.py`, `policies.py`) with extensive test coverage, but nothing
exposes them over HTTP yet. Introducing that HTTP contract (request/response
shape, versioning, pagination, error format) is real, separate design work —
not a rename of existing functions — and belongs to its own future phase
(see `docs/EVENT_BACKBONE.md`: "API idempotency headers: Phase 10 API /
Integration Contract Suite").

## What Is Actually Exposed Over HTTP Today

| Endpoint | Method | Auth | Purpose |
| --- | --- | --- | --- |
| `/api/health/` | GET | none | Liveness check. |
| `/api/portals/parent/login/` | POST | none (rate-limited, `parent_login` scope) | Stub parent-login request; always returns a generic 202 regardless of whether the admission number exists, to avoid enumeration. The "send a real code" step is intentionally not implemented yet. |
| `/api/observability/metrics/` | GET | shared-secret header outside `DEBUG` | Prometheus metrics. See `docs/OBSERVABILITY.md`. |
| `/api/schema/`, `/api/docs/`, `/api/redoc/` | GET | staff-only outside `DEBUG` | Live OpenAPI schema / Swagger UI / ReDoc for the endpoints above, via `drf-spectacular`. |
| `/admin/` | — | Django staff auth | Django admin. |

That is the entire real HTTP surface. Everything else in this repository
(grading workflows, CCT evidence submission, curriculum publication,
readiness dashboards, report snapshots, event contracts) is tested and
exercised at the Python service-layer only.

## Why This Matters For Reviewers

Do not infer API maturity from the phase documentation alone. The phase docs
(`docs/ARCHITECTURE_PHASES.md`, `docs/GRADING_ENGINE.md`,
`docs/CCT_SECURITY_MODEL.md`) describe a very deep, deliberately-scoped
**domain and service layer** with strong tenant isolation, ABAC, and
audit/immutability guarantees. The HTTP layer on top of that domain layer is,
by contrast, still almost entirely unbuilt. Both facts are true at once.

## Foundation

- Django project layout lives under `app/`.
- Runtime is Dockerized with PostgreSQL, Redis, Celery worker, Celery beat, and
  Toxiproxy.
- CI is split into diagnostic gates for validation, linting, security scanning,
  Django smoke checks, unit tests, and Docker build verification.
- Domain directories are prepared as future modular-monolith boundaries.

## Testing

Normal tests exclude chaos checks by default:

```bash
make test
```

Chaos checks are opt-in:

```bash
make test-chaos
```
