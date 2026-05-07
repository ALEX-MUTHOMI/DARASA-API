# Darasa-Core API Documentation

This document is intentionally minimal during Phase 1. The current repository
contains runtime foundation, automation, and future domain boundaries only.

## Phase 1 Status

- Django project layout lives under `app/`.
- Runtime is Dockerized with PostgreSQL, Redis, Celery worker, Celery beat, and
  Toxiproxy.
- CI is split into diagnostic gates for validation, linting, security scanning,
  Django smoke checks, unit tests, and Docker build verification.
- Domain directories are prepared as future modular-monolith boundaries.

## API Surface

No business API surface is documented in Phase 1. Endpoint documentation will be
added only when later phases intentionally introduce implemented application
behavior.

## Testing

Normal tests exclude chaos checks by default:

```bash
make test
```

Chaos checks are opt-in:

```bash
make test-chaos
```
