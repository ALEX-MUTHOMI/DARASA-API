#!/usr/bin/env bash
set -eo pipefail

MODE="${1:-unit}"
PYTEST_CONFIG_ARGS=()
PHASE2_MARKER_EXPRESSION="not chaos and not phase3 and not phase4 and not phase5 and not phase6 and not future"
PYTEST_COMMAND=(pytest)

if [ "$#" -gt 0 ]; then
  shift
fi

if [ -f "/workspace/pyproject.toml" ]; then
  cd /workspace
elif [ ! -f "pyproject.toml" ] && [ -f "../pyproject.toml" ]; then
  cd ..
elif [ ! -f "pyproject.toml" ] && [ -f "app/manage.py" ]; then
  :
fi

if [ -f "pytest.ini" ]; then
  PYTEST_CONFIG_ARGS=(-c pytest.ini)
fi

if command -v poetry >/dev/null 2>&1; then
  PYTEST_COMMAND=(poetry run pytest)
fi

case "${MODE}" in
  unit|default|phase1|phase2)
    echo "Running Phase 2-safe pytest selection"
    exec "${PYTEST_COMMAND[@]}" "${PYTEST_CONFIG_ARGS[@]}" -m "${PHASE2_MARKER_EXPRESSION}" "$@"
    ;;
  phase3|phase4|phase5|phase6|future|integration)
    echo "Running opt-in pytest marker: ${MODE}"
    exec "${PYTEST_COMMAND[@]}" "${PYTEST_CONFIG_ARGS[@]}" -m "${MODE}" "$@"
    ;;
  chaos)
    echo "Running opt-in chaos tests"
    export DARASA_CHAOS_TESTS_ENABLED="${DARASA_CHAOS_TESTS_ENABLED:-1}"
    exec "${PYTEST_COMMAND[@]}" "${PYTEST_CONFIG_ARGS[@]}" -m "chaos" "$@"
    ;;
  all)
    echo "Running all tests"
    exec "${PYTEST_COMMAND[@]}" "${PYTEST_CONFIG_ARGS[@]}" "$@"
    ;;
  *)
    echo "Running pytest passthrough: ${MODE} $*"
    exec "${PYTEST_COMMAND[@]}" "${PYTEST_CONFIG_ARGS[@]}" "${MODE}" "$@"
    ;;
esac
