# Darasa-Core

Darasa-Core is the backend foundation for an academic ERP for schools. Phase 1
focuses on deterministic runtime, automation, tenant-readiness, observability,
security posture, and service-boundary scaffolding.

## Phase 1 Scope

- Dockerized Django runtime on Python 3.11.
- Poetry-managed dependencies with diagnostic CI gates.
- PostgreSQL, Redis, Celery worker, Celery beat, and Toxiproxy in Compose.
- Multi-tenant-ready Django project layout under `app/`.
- CQRS-oriented domain scaffolding for later academic ERP phases.
- Security, test, and chaos-engineering gatekeepers.

## Local Commands

```bash
make build
make django-check
make lint
make security
make test
```

Chaos tests are opt-in:

```bash
make test-chaos
```

## Runtime Layout

- Django project: `app/darasa_project`
- Django entrypoint: `app/manage.py`
- Container app workdir: `/app`
- Container script mount: `/scripts`

## Boundary

Darasa-Core handles academic ERP foundations only. Non-academic commercial
workflows are intentionally outside this repository.
