# Developer Onboarding

Start with the Docker workflow because it matches CI.

```bash
docker compose config -q
docker compose run --rm django bash /workspace/scripts/run-tests.sh patch
docker compose run --rm django bash -c "cd /workspace/app && python manage.py check"
```

Host Poetry is optional for day-to-day work. If you use it locally, install the
same dependency groups declared in `pyproject.toml` and select the Poetry
interpreter in VS Code.

## Test Gates

Darasa uses layered gates to avoid wasting hours during normal iteration while
keeping phase closeout strict.

```bash
docker compose run --rm django bash /workspace/scripts/run-tests.sh patch
docker compose run --rm django bash /workspace/scripts/run-tests.sh domain curriculum
docker compose run --rm django bash /workspace/scripts/run-tests.sh full
docker compose run --rm django bash /workspace/scripts/run-tests.sh deep
```

Patch/Turbo Pass is a developer-feedback gate, not a merge/release gate. Use
Domain Gates after changing curriculum, grading, events, core, tenant, or
academics. Use Full Gate for phase closeout. Use Deep Gate for CCT, grading,
security, red-team, performance, and production-risk closeouts.

See `docs/TESTING_STRATEGY.md` for the Codex routing rules.

## Phase Markers

Default tests include the active phase surface. Future phases,
integration-heavy tests, and chaos tests are opt-in. Do not remove phase or
security markers to make tests pass; fix the boundary or the implementation.

## Migration Discipline

Run a full active-app migration check before handing off work:

```bash
docker compose run --rm django bash -c "cd /workspace/app && python manage.py makemigrations --check --dry-run"
```

Expected result is `No changes detected`.

## Security Checks

Run lint, Bandit, dependency audit, and compile checks before opening a PR:

```bash
docker compose run --rm django bash -c "cd /workspace && flake8 app"
docker compose run --rm django bash -c "cd /workspace && bandit -r app -c pyproject.toml"
docker compose run --rm django bash -c "cd /workspace && pip-audit"
python -m compileall app
```

## CCT Development Rules

CCT algorithms must remain deterministic and offline. Do not add live web calls,
browser automation, AI parsing, automatic source polling, or automatic
publication. Add source evidence and workflow tests for every hardening change.

Evidence uploads are metadata-only backend contracts until production storage
is attached. Principals and deputies submit quarantined evidence, not
curriculum truth. Do not accept client-controlled scan status, content
verification status, reviewer, publisher, publication, adoption, or rollback
state. Governance approval requires a verification report plus clean malware
status and passed content verification, and production upload endpoints must
also enforce step-up confirmation, rate limits, private storage, and audit
logging.

## Production Readiness Backlog

Use `docs/PRODUCTION_READINESS_BACKLOG.md` as the canonical source for work
that remains before national production rollout. Do not treat backlog entries
as complete because the application contract exists. Public CCT uploads,
national rollout, reports, and production operations require their listed
infrastructure, security, observability, and governance acceptance criteria.
