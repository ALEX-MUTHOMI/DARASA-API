#!/usr/bin/env bash
set -eo pipefail

MODE="${1:-unit}"
PYTEST_CONFIG_ARGS=()

if [ "$#" -gt 0 ]; then
  shift
fi

if [ ! -f "manage.py" ] && [ ! -f "pyproject.toml" ] && [ -f "app/manage.py" ]; then
  cd app
fi

if [ -f "pytest.ini" ]; then
  PYTEST_CONFIG_ARGS=(-c pytest.ini)
fi

case "${MODE}" in
  unit|default)
    echo "Running pytest without chaos tests"
    exec poetry run pytest "${PYTEST_CONFIG_ARGS[@]}" -m "not chaos" "$@"
    ;;
  chaos)
    echo "Running opt-in chaos tests"
    export DARASA_CHAOS_TESTS_ENABLED="${DARASA_CHAOS_TESTS_ENABLED:-1}"
    exec poetry run pytest "${PYTEST_CONFIG_ARGS[@]}" -m "chaos" "$@"
    ;;
  all)
    echo "Running all tests"
    exec poetry run pytest "${PYTEST_CONFIG_ARGS[@]}" "$@"
    ;;
  *)
    echo "Running pytest passthrough: ${MODE} $*"
    exec poetry run pytest "${PYTEST_CONFIG_ARGS[@]}" "${MODE}" "$@"
    ;;
esac
