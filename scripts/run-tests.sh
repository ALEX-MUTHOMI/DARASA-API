#!/bin/sh
# ─────────────────────────────────────────────────────────────────────────────
# Darasa-Core Enterprise Test Runner
# Back To Front Development
#
# Usage (via Docker Compose):
#   docker compose run --rm test unit        — fast unit tests (no external services)
#   docker compose run --rm test integration — DB + Redis integration tests
#   docker compose run --rm test security    — adversarial / IDOR / isolation tests
#   docker compose run --rm test chaos       — Toxiproxy fault-injection tests
#   docker compose run --rm test celery      — Celery task pipeline tests
#   docker compose run --rm test mutation    — mutmut mutation testing baseline
#   docker compose run --rm test coverage    — full suite with coverage report
#   docker compose run --rm test flake8      — lint
#   docker compose run --rm test all         — everything
# ─────────────────────────────────────────────────────────────────────────────
set -e

SUITE="${1:-unit}"

# Pass-through: allows raw pytest/python commands for quick debugging
if [ "$SUITE" = "pytest" ] || [ "$SUITE" = "python" ]; then
  echo "[INFO] Raw command passthrough: $*"
  exec "$@"
fi

shift 1 || true
EXTRA_ARGS="$@"

echo "================================================================"
echo "  Darasa-Core Enterprise Test Runner"
echo "  Suite    : $SUITE"
echo "  Extra    : $EXTRA_ARGS"
echo "  Workdir  : $(pwd)"
echo "  Python   : $(python --version)"
echo "  Pytest   : $(python -m pytest --version)"
echo "================================================================"

# Clean stale bytecode — prevents ghost failures from cached .pyc files
find . -name "*.pyc" -delete 2>/dev/null || true
find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
rm -rf .pytest_cache 2>/dev/null || true

echo ""

# ─────────────────────────────────────────────────────────────────────────────
# Wait for the database before running any suite that needs DB access
# ─────────────────────────────────────────────────────────────────────────────
_wait_for_db() {
  echo "[INFO] Waiting for database..."
  python -c "
import os, sys, time, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'darasa_project.settings')
django.setup()
from django.db import connections
from django.db.utils import OperationalError
for i in range(30):
    try:
        connections['default'].ensure_connection()
        print('[INFO] Database is ready.')
        sys.exit(0)
    except OperationalError:
        print(f'[INFO] DB not ready, retry {i+1}/30...')
        time.sleep(2)
print('[ERROR] Database not available after 60s.')
sys.exit(1)
"
}

# ─────────────────────────────────────────────────────────────────────────────
# Run shared schema migrations (public schema only — tenant schemas
# are migrated per-tenant on onboarding, not globally here)
# ─────────────────────────────────────────────────────────────────────────────
_run_migrations() {
  echo "[INFO] Running shared schema migrations..."
  TMP_ROOT="${TMPDIR:-/var/tmp}"
  mkdir -p "$TMP_ROOT"
  MIGRATE_LOG="$TMP_ROOT/darasa-migrate-$$.log"
  if ! python manage.py migrate_schemas --shared --no-input >"$MIGRATE_LOG" 2>&1; then
    tail -20 "$MIGRATE_LOG"
    rm -f "$MIGRATE_LOG"
    exit 1
  fi
  tail -5 "$MIGRATE_LOG"
  rm -f "$MIGRATE_LOG"
  echo ""
}

case "$SUITE" in

  # ── UNIT: pure logic, no DB, no network ─────────────────────────────────
  unit)
    echo "[RUNNING] Unit tests (no external services required)..."
    exec python -m pytest \
      -m "unit" \
      --timeout=30 -v --tb=short \
      $EXTRA_ARGS
    ;;

  # ── INTEGRATION: requires DB + Redis ────────────────────────────────────
  integration)
    _wait_for_db
    _run_migrations
    echo "[RUNNING] Integration tests (DB + Redis)..."
    exec python -m pytest \
      -m "integration" \
      --timeout=60 -v --tb=short \
      $EXTRA_ARGS
    ;;

  # ── SECURITY: IDOR, tenant isolation, JWT attacks, schema leakage ───────
  security)
    _wait_for_db
    _run_migrations
    echo "[RUNNING] Security test suite..."
    exec python -m pytest \
      -m "security" \
      --timeout=60 -v --tb=short \
      $EXTRA_ARGS
    ;;

  # ── CHAOS: Toxiproxy network fault injection ─────────────────────────────
  chaos)
    _wait_for_db
    _run_migrations
    echo "[RUNNING] Chaos / fault-injection tests (via Toxiproxy)..."
    exec python -m pytest \
      -m "chaos" \
      --timeout=120 -v --tb=short \
      $EXTRA_ARGS
    ;;

  # ── CELERY: task pipeline tests ──────────────────────────────────────────
  celery)
    _wait_for_db
    _run_migrations
    echo "[RUNNING] Celery pipeline tests..."
    exec python -m pytest \
      -m "celery" \
      --timeout=60 -v --tb=short \
      $EXTRA_ARGS
    ;;

  # ── MUTATION: mutmut baseline mutation testing ───────────────────────────
  mutation)
    echo "[RUNNING] Mutation testing baseline (mutmut)..."
    exec python -m mutmut run \
      --paths-to-mutate darasa_project/ \
      --runner "python -m pytest -x -q" \
      $EXTRA_ARGS
    ;;

  # ── COVERAGE: full suite with HTML + term report ─────────────────────────
  coverage)
    _wait_for_db
    _run_migrations
    echo "[RUNNING] Coverage analysis (full suite)..."
    exec python -m pytest \
      --cov=. \
      --cov-report=term-missing \
      --cov-report=html:htmlcov \
      --cov-fail-under=80 \
      --timeout=120 -v --tb=short \
      $EXTRA_ARGS
    ;;

  # ── ALL: everything ───────────────────────────────────────────────────────
  all)
    _wait_for_db
    _run_migrations
    echo "[RUNNING] Full system suite..."
    exec python -m pytest \
      --timeout=180 -v --tb=short \
      $EXTRA_ARGS
    ;;

  # ── FLAKE8: lint ──────────────────────────────────────────────────────────
  flake8)
    echo "[RUNNING] flake8 lint check..."
    exec python -m flake8 \
      --config /app/.flake8 \
      --count \
      --statistics \
      . $EXTRA_ARGS
    ;;

  *)
    echo "ERROR: Unknown suite '$SUITE'"
    echo ""
    echo "Usage: docker compose run --rm test [SUITE]"
    echo ""
    echo "Suites:"
    echo "  unit        — Pure unit tests (no DB, no network)"
    echo "  integration — DB + Redis integration tests"
    echo "  security    — Adversarial / IDOR / tenant isolation tests"
    echo "  chaos       — Toxiproxy network fault injection"
    echo "  celery      — Celery task pipeline tests"
    echo "  mutation    — mutmut mutation testing baseline"
    echo "  coverage    — Full suite with HTML coverage report"
    echo "  flake8      — Lint the codebase"
    echo "  all         — Everything"
    exit 1
    ;;
esac
