#!/bin/sh
# ─────────────────────────────────────────────────────────────────────────────
# run.sh — Darasa-Core production entrypoint
# Back To Front Development
#
# Executed as CMD inside the Docker container for the `app` service.
# For the `celery` service, docker-compose.yml overrides CMD directly.
# ─────────────────────────────────────────────────────────────────────────────
set -e

echo "[INFO] Starting Darasa-Core..."
echo "[INFO] Python: $(python --version)"
echo "[INFO] Django: $(python -c 'import django; print(django.__version__)')"

# Wait for DB to be reachable before running gunicorn
python manage.py wait_for_db

# Migrate shared schema (public schema — tenant registry, billing, etc.)
python manage.py migrate_schemas --shared --no-input

# Collect static files for Nginx/CDN serving
python manage.py collectstatic --no-input

echo "[INFO] Launching Gunicorn..."
exec gunicorn \
    darasa_project.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers "${GUNICORN_WORKERS:-4}" \
    --worker-class sync \
    --timeout "${GUNICORN_TIMEOUT:-30}" \
    --max-requests 1000 \
    --max-requests-jitter 100 \
    --log-level info \
    --access-logfile - \
    --error-logfile -