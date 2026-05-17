#!/usr/bin/env bash
set -eo pipefail

MODE="${1:-unit}"
shift || true

PYTEST_CONFIG_ARGS=()
PYTEST_COMMAND=(pytest)
DEFAULT_MARKER_EXPRESSION="not chaos and not integration and not future"

if [ -f "/workspace/pyproject.toml" ]; then
  cd /workspace
elif [ ! -f "pyproject.toml" ] && [ -f "../pyproject.toml" ]; then
  cd ..
fi

if [ -f "pytest.ini" ]; then
  PYTEST_CONFIG_ARGS=(-c pytest.ini)
fi

if command -v poetry >/dev/null 2>&1; then
  PYTEST_COMMAND=(poetry run pytest)
fi

run_pytest() {
  "${PYTEST_COMMAND[@]}" "${PYTEST_CONFIG_ARGS[@]}" "$@"
}

run_manage() {
  (cd app && python manage.py "$@")
}

run_optional_file() {
  local test_path="$1"
  shift
  if [ -f "$test_path" ]; then
    run_pytest "$test_path" "$@"
  else
    echo "Skipping missing optional test file: $test_path"
  fi
}

run_check_and_migrations() {
  run_manage check
  run_manage makemigrations --check --dry-run
}

run_unit() {
  echo "Running default unit test selection"
  run_pytest -m "$DEFAULT_MARKER_EXPRESSION" "$@"
}

run_patch() {
  echo "Running Patch/Turbo Gate"
  run_check_and_migrations
  flake8 app
  run_pytest \
    app/curriculum/tests/test_cct_fortification_control_plane.py \
    app/grading/tests/test_phase6a_cbe_cct_binding.py \
    -q
}

run_domain_curriculum() {
  echo "Running Domain Gate: curriculum"
  run_check_and_migrations
  local paths=(
    app/curriculum/tests
    app/grading/tests/test_phase6a_cbe_cct_binding.py
  )
  if [ -f app/grading/tests/test_phase6c_compilation_services.py ]; then
    paths+=(app/grading/tests/test_phase6c_compilation_services.py)
  else
    echo "Skipping missing optional test file: app/grading/tests/test_phase6c_compilation_services.py"
  fi
  run_pytest "${paths[@]}" -q
  flake8 app
}

run_domain_grading() {
  echo "Running Domain Gate: grading"
  run_check_and_migrations
  run_pytest \
    app/grading/tests \
    app/curriculum/tests/test_cct_fortification_control_plane.py \
    -q
  flake8 app
}

run_domain_events() {
  echo "Running Domain Gate: events"
  run_check_and_migrations
  if [ -d app/events/tests ]; then
    run_pytest app/events/tests -q
  fi
  run_pytest app/curriculum/tests -k "event or payload" -q
  run_pytest app/grading/tests -k "event or payload" -q
  flake8 app
}

run_domain_core() {
  echo "Running Domain Gate: core/tenant/identity"
  run_check_and_migrations
  run_pytest app/core/tests app/tenant/tests app/curriculum/tests app/grading/tests -q
  flake8 app
}

run_domain_academics() {
  echo "Running Domain Gate: academics"
  run_check_and_migrations
  run_pytest app/academics/tests app/grading/tests -q
  flake8 app
}

run_domain() {
  local domain="${1:-}"
  shift || true
  case "$domain" in
    curriculum|cct)
      run_domain_curriculum "$@"
      ;;
    grading)
      run_domain_grading "$@"
      ;;
    events)
      run_domain_events "$@"
      ;;
    core|tenant|identity)
      run_domain_core "$@"
      ;;
    academics)
      run_domain_academics "$@"
      ;;
    *)
      echo "Usage: $0 domain {curriculum|grading|events|core|tenant|academics}"
      exit 2
      ;;
  esac
}

run_full() {
  echo "Running Full Gate"
  run_check_and_migrations
  run_manage migrate --noinput
  run_unit "$@"
  flake8 app
  bandit -r app -c pyproject.toml
  pip-audit
  python -m compileall app
  if command -v git >/dev/null 2>&1; then
    git diff --check
  else
    echo "Skipping git diff --check: git is not available."
  fi
}

run_deep() {
  echo "Running Deep Gate"
  run_pytest -m "redteam or security or performance or boundary" -q
  bandit -r app -c pyproject.toml
  pip-audit
  python -m compileall app
  if command -v rg >/dev/null 2>&1; then
    rg -n "requests\\.|httpx\\.|urllib\\.request|aiohttp|selenium|playwright" \
      app/curriculum app/grading --glob "*.py" --glob "!**/tests/**" \
      --glob "!**/migrations/**" && exit 1 || true
    rg -n "raw_marks|learner_names|guardian_phone|raw_circular_text" \
      app --glob "*.py" --glob "!**/tests/**" --glob "!**/migrations/**" \
      --glob "!app/events/algorithms/payload_safety_guard.py" && exit 1 || true
  else
    echo "Skipping Deep Gate ripgrep scans: rg is not available."
  fi
}

suggest_changed_gate() {
  local changed
  changed="$(git diff --name-only 2>/dev/null || true)"
  if [ -z "$changed" ]; then
    changed="$(git diff --name-only --cached 2>/dev/null || true)"
  fi
  if [ -z "$changed" ]; then
    echo "No changed files detected. Suggested gate: patch"
    return
  fi

  echo "$changed"
  echo
  if echo "$changed" | grep -Eq "^(pyproject.toml|Dockerfile|docker-compose.yml|compose.yml|.github/)"; then
    echo "Suggested gate: full"
  elif echo "$changed" | grep -Eq "^app/curriculum/|^app/events/"; then
    echo "Suggested gate: domain curriculum or domain events, then deep if security behavior changed"
  elif echo "$changed" | grep -Eq "^app/grading/"; then
    echo "Suggested gate: domain grading"
  elif echo "$changed" | grep -Eq "^app/(core|tenant)/"; then
    echo "Suggested gate: domain core"
  elif echo "$changed" | grep -Eq "^app/academics/"; then
    echo "Suggested gate: domain academics"
  elif echo "$changed" | grep -Eq "^docs/"; then
    echo "Suggested gate: patch"
  elif echo "$changed" | grep -Eq "/migrations/"; then
    echo "Suggested gate: migration check plus relevant domain gate"
  else
    echo "Suggested gate: patch"
  fi
}

case "$MODE" in
  patch|turbo)
    run_patch "$@"
    ;;
  domain)
    run_domain "$@"
    ;;
  full)
    run_full "$@"
    ;;
  deep)
    run_deep "$@"
    ;;
  changed)
    suggest_changed_gate
    ;;
  unit|default|phase1|phase2|phase3|phase4|phase5|phase6)
    run_unit "$@"
    ;;
  phase6b|future|integration)
    echo "Running opt-in pytest marker: ${MODE}"
    run_pytest -m "$MODE" "$@"
    ;;
  chaos)
    echo "Running opt-in chaos tests"
    export DARASA_CHAOS_TESTS_ENABLED="${DARASA_CHAOS_TESTS_ENABLED:-1}"
    run_pytest -m "chaos" "$@"
    ;;
  all)
    echo "Running all tests"
    run_pytest "$@"
    ;;
  *)
    echo "Running pytest passthrough: ${MODE} $*"
    run_pytest "$MODE" "$@"
    ;;
esac
