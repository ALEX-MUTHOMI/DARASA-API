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

## Developer Environment

Darasa-Core is Docker-first and Poetry-compatible. CI is the source of truth for
quality gates; VS Code should use either the Poetry virtual environment or the
Docker Compose commands above. See `docs/DEVELOPER_ENVIRONMENT.md` for Pylance,
Pylint, and interpreter setup guidance.

## Runtime Layout

- Django project: `app/darasa_project`
- Django entrypoint: `app/manage.py`
- Production image workdir: `/app`
- Production image scripts: `/scripts`
- Docker Compose development workspace: `/workspace`
- Docker Compose development scripts: `/workspace/scripts`

The production image copies `app/` to `/app` and `scripts/` to `/scripts`.
The development Compose stack bind-mounts the repository root at `/workspace`
so Poetry can see `pyproject.toml`, `.flake8`, and `poetry.lock` without nested
file mounts inside `/app`. Django commands should run from `/workspace/app`
when using Compose.

## Boundary

Darasa-Core handles academic ERP foundations only. Non-academic commercial
workflows are intentionally outside this repository.
