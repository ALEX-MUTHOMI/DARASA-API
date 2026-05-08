# Developer Environment

Darasa-Core is Docker-first and Poetry-compatible.

CI is the source of truth for quality gates. Local IDE diagnostics should match
the same dependency set and nested Django layout used by Docker and GitHub
Actions.

## Recommended Flow: Docker-First

Use Docker Compose when you want the closest match to CI and production:

```bash
make build
make django-check
make lint
make security
make test
```

On Windows hosts without `make`, run the equivalent Compose commands:

```bash
docker compose build
docker compose run --rm django bash -c "cd /workspace/app && python manage.py check"
docker compose run --rm django bash -c "cd /workspace && flake8 app"
docker compose run --rm django bash -c "cd /workspace && bandit -r app -c pyproject.toml && pip-audit"
docker compose run --rm django bash /workspace/scripts/run-tests.sh unit
```

The Compose workspace is `/workspace`. Django commands run from
`/workspace/app`.

## Optional Flow: Local Poetry

Use this when you want VS Code/Pylance/Pylint to resolve Django and dependency
imports directly on the host:

```bash
poetry install --with dev,security,chaos
poetry env info --path
```

Then in VS Code:

1. Run `Python: Select Interpreter`.
2. Select the interpreter from the Poetry environment path.
3. Reload the VS Code window.

If VS Code uses a system Python without project dependencies, Pylance may report
missing imports for packages such as Django or Cryptography even though Docker
and CI are healthy.

## VS Code Layout

The project uses a nested Django layout:

```text
repo-root/
├── pyproject.toml
├── docker-compose.yml
└── app/
    ├── manage.py
    └── darasa_project/
```

Workspace settings add `app/` to Python analysis paths so imports such as
`darasa_project.settings`, `core.models`, and `tenant.models` resolve.

## Pylance and Django ORM

Django creates ORM attributes dynamically, including foreign-key convenience
attributes such as `user_id`, `tenant_id`, and `role_id`. Pylance can warn about
these because they are not declared as normal Python attributes.

This repository keeps Pylance in basic mode and downgrades dynamic attribute
diagnostics to warnings. Runtime correctness remains enforced by:

- Django system checks
- migrations
- pytest
- Flake8
- Bandit
- pip-audit

## Pylint Policy

Pylint is not a CI gate for Darasa-Core. Flake8 is the official style gate.

The local Pylint config suppresses convention-only noise such as missing
docstrings and common Django ORM dynamic-attribute false positives. It does not
replace CI security or lint checks.

## Troubleshooting

If Pylance says `Import "django..." could not be resolved`:

1. Confirm VS Code selected the Poetry interpreter, or use Docker-first commands.
2. Confirm `.vscode/settings.json` includes `app` in `python.analysis.extraPaths`.
3. Reload the VS Code window.

If Pylint says dependencies cannot be imported, the selected interpreter does
not have the Poetry dependencies installed.
