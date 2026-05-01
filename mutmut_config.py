# =============================================================================
# mutmut_config.py — Darasa-Core Mutation Testing Configuration
# Back To Front Development
#
# PHILOSOPHY:
#   Mutmut surgically targets our core business logic algorithms ONLY.
#   Mutating test files, migrations, settings, or scaffolding is a waste of
#   CI compute time and produces noise with zero signal.
#
# HARD EXCLUSION LIST (pre_mutation hook):
#   - tests/           — test files cannot test themselves
#   - migrations/      — auto-generated, no business logic
#   - manage.py        — Django entrypoint, no logic
#   - settings.py      — config, not logic
#   - wsgi.py          — WSGI adapter, no logic
#   - asgi.py          — ASGI adapter, no logic
#   - apps.py          — AppConfig scaffolding, no logic
#   - conftest.py      — pytest fixtures, not production code
#   - factories.py     — test factories, not production code
#   - admin.py         — Django admin registration, no logic
#
# TARGET DOMAINS (where surviving mutants = real bugs):
#   - core/algorithms.py        — CircuitBreaker, @idempotent
#   - core/models.py            — EncryptedCharField, UUID logic
#   - academics/                — CBC grade computation
#   - grading/                  — Competency scoring algorithms
#   - curriculum/               — Strand/sub-strand mapping logic
#   - bus/                      — Event bus routing logic
#   - tenant/                   — Schema provisioning logic
# =============================================================================

import os


def init():
    """
    Called once by mutmut before any mutations begin.
    Use this to set up any global state if needed.
    """
    pass  # No global state required


# Files / patterns that mutmut should NEVER mutate.
# This list is evaluated inside the pre_mutation hook below.
_EXCLUDED_PATTERNS = (
    # Test infrastructure
    "/tests/",
    "test_",
    "_test.py",
    "conftest.py",
    "factories.py",
    "factory.py",
    # Django migrations
    "/migrations/",
    # Django scaffolding & entrypoints
    "manage.py",
    "settings.py",
    "wsgi.py",
    "asgi.py",
    "apps.py",
    "admin.py",
    "urls.py",
    # Setup / packaging
    "setup.py",
    "setup.cfg",
    # Scripts
    "/scripts/",
)


def pre_mutation(context):
    """
    Called by mutmut before each individual mutation.

    Returning `context.skip = True` tells mutmut to skip this mutant entirely
    without running the test suite — saving significant CI compute time.

    CONTRACT: Only pure business logic files are mutated.
    Scaffolding, config, test code, and migrations are NEVER touched.
    """
    src_path = context.filename

    for pattern in _EXCLUDED_PATTERNS:
        if pattern in src_path:
            context.skip = True
            return

    # Additional guard: skip any file outside our known domain apps.
    # This prevents mutmut from accidentally targeting vendor files
    # or any dynamically loaded Python files outside the project root.
    _ALLOWED_DOMAINS = (
        "core/",
        "tenant/",
        "bus/",
        "academics/",
        "grading/",
        "curriculum/",
        "disciplinary/",
        "portals/",
        "darasa_project/",
    )
    if not any(domain in src_path for domain in _ALLOWED_DOMAINS):
        context.skip = True
        return

    # Log what we ARE mutating so CI output is auditable
    print(f"[mutmut] Mutating: {src_path}:{context.current_line_index}")
