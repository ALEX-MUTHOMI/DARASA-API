#!/usr/bin/env bash
set -eo pipefail

PROJECT_NAME="darasa_project"

DOMAIN_APPS=(
  "tenant"
  "core"
  "staff"
  "academics"
  "curriculum"
  "grading"
  "reports"
  "schemes"
  "lesson_assistant"
  "bus"
  "audit"
  "observability"
  "chaos"
)

ALGORITHM_APPS=(
  "curriculum"
  "grading"
  "reports"
  "schemes"
  "lesson_assistant"
)

CQRS_FILES=(
  "services.py"
  "selectors.py"
  "policies.py"
  "events.py"
  "tasks.py"
)

HOST_UID="${HOST_UID:-$(id -u)}"
HOST_GID="${HOST_GID:-$(id -g)}"

echo "Scaffolding Darasa-Core project and domain boundaries"

if [ ! -f "manage.py" ] && [ -f "app/manage.py" ]; then
  cd app
fi

if [ ! -f "manage.py" ] || [ ! -d "${PROJECT_NAME}" ]; then
  if [ -e "manage.py" ] || [ -e "${PROJECT_NAME}" ]; then
    echo "Partial Django project detected. Refusing to overwrite developer work."
    exit 1
  fi

  django-admin startproject "${PROJECT_NAME}" .
fi

for domain in "${DOMAIN_APPS[@]}"; do
  if [ ! -d "${domain}" ]; then
    django-admin startapp "${domain}"
  fi

  mkdir -p "${domain}/tests"
  touch "${domain}/tests/__init__.py"

  for file_name in "${CQRS_FILES[@]}"; do
    touch "${domain}/${file_name}"
  done
done

for domain in "${ALGORITHM_APPS[@]}"; do
  touch "${domain}/algorithms.py"
done

if command -v chown >/dev/null 2>&1; then
  chown -R "${HOST_UID}:${HOST_GID}" . || {
    echo "Warning: unable to chown generated files to ${HOST_UID}:${HOST_GID}"
  }
fi

echo "Scaffold complete"
