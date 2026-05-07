#!/usr/bin/env bash
set -eo pipefail

APP_MODULE="${DJANGO_WSGI_MODULE:-darasa_project.wsgi:application}"
HOST="${GUNICORN_BIND_HOST:-0.0.0.0}"
PORT="${GUNICORN_BIND_PORT:-8000}"
WORKERS="${GUNICORN_WORKERS:-3}"
TIMEOUT="${GUNICORN_TIMEOUT:-60}"
LOG_LEVEL="${GUNICORN_LOG_LEVEL:-info}"

echo "Starting Darasa-Core Django runtime"
echo "Python: $(python --version)"

if [ ! -f "manage.py" ] && [ -f "app/manage.py" ]; then
  cd app
fi

if [ ! -f "manage.py" ]; then
  echo "manage.py not found in $(pwd)"
  exit 1
fi

echo "Waiting for database readiness"
python manage.py wait_for_db

echo "Running Django system checks"
python manage.py check

echo "Launching Gunicorn on ${HOST}:${PORT}"
exec gunicorn "${APP_MODULE}" \
  --bind "${HOST}:${PORT}" \
  --workers "${WORKERS}" \
  --worker-class sync \
  --timeout "${TIMEOUT}" \
  --access-logfile - \
  --error-logfile - \
  --log-level "${LOG_LEVEL}"
