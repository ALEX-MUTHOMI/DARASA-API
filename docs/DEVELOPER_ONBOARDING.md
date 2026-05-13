# Developer Onboarding

Start with the Docker workflow because it matches CI.

```bash
docker compose config -q
docker compose run --rm django bash /workspace/scripts/run-tests.sh unit
docker compose run --rm django bash -c "cd /workspace/app && python manage.py check"
```

Host Poetry is optional for day-to-day work. If you use it locally, install the
same dependency groups declared in `pyproject.toml` and select the Poetry
interpreter in VS Code.

## Phase Markers

Default tests include Phase 1 through Phase 4C. Future phases, integration-heavy
tests, and chaos tests are opt-in. Do not remove phase markers to make tests
pass; fix the boundary or the implementation.

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
