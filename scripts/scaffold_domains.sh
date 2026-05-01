#!/bin/bash
# =============================================================================
# scaffold_domains.sh — Darasa-Core Project & Domain Initialization
# Back To Front Development
#
# PURPOSE:
#   1. Initializes the Django project (darasa_project) if it does not exist.
#   2. Scaffolds all 8 isolated domain apps for the CBC ERP system.
#   3. Fixes file ownership back to the host user (prevents root-locked files
#      on the host machine after Docker writes them as root).
#
# IDEMPOTENCY CONTRACT:
#   Every startproject/startapp call is guarded by a directory existence check.
#   Running this script multiple times is completely safe — it will only
#   create what does not yet exist.
#
# DOCKER PERMISSION FIX:
#   Files created by Django inside Docker are owned by root (UID 0).
#   The final chown step restores ownership to HOST_UID:HOST_GID so the
#   developer can edit files on the host without sudo.
#
# USAGE (via Makefile — DO NOT run outside Docker):
#   docker compose run --rm -e HOST_UID=$(id -u) -e HOST_GID=$(id -g) \
#       app bash /scripts/scaffold_domains.sh
#
# FAIL-FAST:
#   -e  : exit immediately on any command failure
#   -o pipefail : pipe failures are treated as errors
# =============================================================================
set -eo pipefail

# ── Colour codes ──────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# ── Configuration ─────────────────────────────────────────────────────────────
PROJECT_NAME="darasa_project"

# The 8 isolated CBC domain apps — each is its own bounded context.
# Cross-domain DB joins between these are STRICTLY FORBIDDEN.
DOMAIN_APPS=(
    "tenant"        # Schema provisioning, School model, tenant lifecycle
    "core"          # CustomUser, EncryptedCharField, shared base models
    "bus"           # Event bus — async event routing & idempotency locks
    "academics"     # Classes, streams, timetables, CBC academic calendar
    "grading"       # Competency scoring, strand/sub-strand assessment
    "curriculum"    # CBC learning areas, strands, sub-strands, indicators
    "disciplinary"  # Incident management, behaviour tracking, DPA-compliant logging
    "portals"       # Parent portal, teacher portal, admin dashboard APIs
)

echo ""
echo -e "${CYAN}${BOLD}============================================================${NC}"
echo -e "${CYAN}${BOLD}  Darasa-Core — Domain Scaffolding${NC}"
echo -e "${CYAN}${BOLD}  Working directory: $(pwd)${NC}"
echo -e "${CYAN}${BOLD}  Django version:    $(python -c 'import django; print(django.__version__)')${NC}"
echo -e "${CYAN}${BOLD}============================================================${NC}"
echo ""

# ── CONTRACT: Verify we are in /app with Django available ────────────────────
python -c "import django" 2>/dev/null || {
    echo -e "${RED}[ERROR] Django is not importable. Is the virtual environment active?${NC}"
    echo -e "${RED}        Ensure DEV=true was set during the Docker image build.${NC}"
    exit 1
}

# ── STEP 1: Initialize Django project ─────────────────────────────────────────
echo -e "${YELLOW}[STEP 1]${NC} Initializing Django project: ${BOLD}${PROJECT_NAME}${NC}"
echo ""

if [ -d "${PROJECT_NAME}" ]; then
    echo -e "  ${YELLOW}[SKIP]${NC} ${PROJECT_NAME}/ already exists — skipping startproject."
else
    echo -e "  ${CYAN}[RUN]${NC}  django-admin startproject ${PROJECT_NAME} ."
    python -m django startproject "${PROJECT_NAME}" .

    # Verify the project was actually created
    if [ ! -d "${PROJECT_NAME}" ]; then
        echo -e "  ${RED}[ERROR]${NC} startproject failed — ${PROJECT_NAME}/ not found after execution."
        exit 1
    fi

    echo -e "  ${GREEN}[OK]${NC}   ${PROJECT_NAME}/ created successfully."
fi

echo ""

# ── STEP 2: Scaffold domain applications ──────────────────────────────────────
echo -e "${YELLOW}[STEP 2]${NC} Scaffolding domain applications..."
echo ""

CREATED_COUNT=0
SKIPPED_COUNT=0

for domain in "${DOMAIN_APPS[@]}"; do
    if [ -d "${domain}" ]; then
        echo -e "  ${YELLOW}[SKIP]${NC}  ${domain}/ already exists — idempotent skip."
        SKIPPED_COUNT=$((SKIPPED_COUNT + 1))
    else
        echo -e "  ${CYAN}[RUN]${NC}   django-admin startapp ${domain}"
        python -m django startapp "${domain}"

        # Verify the app was actually created
        if [ ! -d "${domain}" ]; then
            echo -e "  ${RED}[ERROR]${NC} startapp failed — ${domain}/ not found after execution."
            exit 1
        fi

        # Immediately create the tests/ package structure Django startapp doesn't provide
        mkdir -p "${domain}/tests"
        touch "${domain}/tests/__init__.py"

        # Create domain-standard sub-module stubs
        # These are empty files that will be populated in later phases.
        # Creating them now ensures the import graph is resolvable from Day 1.
        touch "${domain}/services.py"    # Business logic layer (no direct view coupling)
        touch "${domain}/selectors.py"   # Read-only query layer (CQRS-lite pattern)
        touch "${domain}/exceptions.py"  # Domain-specific exception hierarchy

        echo -e "  ${GREEN}[OK]${NC}    ${domain}/ scaffolded with tests/, services.py, selectors.py, exceptions.py"
        CREATED_COUNT=$((CREATED_COUNT + 1))
    fi
done

echo ""

# ── STEP 3: Scaffold conftest.py stubs ────────────────────────────────────────
echo -e "${YELLOW}[STEP 3]${NC} Scaffolding test infrastructure stubs..."
echo ""

# Root-level conftest.py — Toxiproxy fixtures live here (Phase 5)
if [ ! -f "conftest.py" ]; then
    cat > conftest.py << 'CONFTEST_EOF'
"""
conftest.py — Darasa-Core Root Test Configuration
Populated with Toxiproxy fixtures in Phase 5.
"""
import django
import pytest


@pytest.fixture(scope="session")
def django_db_setup():
    """Session-scoped DB setup placeholder. Extended in Phase 5."""
    pass
CONFTEST_EOF
    echo -e "  ${GREEN}[OK]${NC}   conftest.py stub created."
else
    echo -e "  ${YELLOW}[SKIP]${NC} conftest.py already exists."
fi

# pytest.ini — point at the new settings module
if [ ! -f "pytest.ini" ]; then
    cat > pytest.ini << 'PYTEST_EOF'
[pytest]
DJANGO_SETTINGS_MODULE = darasa_project.settings
python_files = test_*.py *_test.py
python_classes = Test*
python_functions = test_*
PYTEST_EOF
    echo -e "  ${GREEN}[OK]${NC}   pytest.ini stub created."
else
    echo -e "  ${YELLOW}[SKIP]${NC} pytest.ini already exists."
fi

echo ""

# ── STEP 4: Fix file ownership (DOCKER PERMISSION FIX) ───────────────────────
# Files created by Django inside Docker are owned by root (UID 0:GID 0).
# Without this fix, the developer cannot edit scaffolded files on their host
# machine without using sudo — a critical DX failure.
#
# HOST_UID and HOST_GID are injected as environment variables by the Makefile:
#   docker compose run -e HOST_UID=$(id -u) -e HOST_GID=$(id -g) ...
echo -e "${YELLOW}[STEP 4]${NC} Fixing file ownership (Docker permission fix)..."
echo ""

# Default to 1000:1000 if not provided (matches most Linux/Mac users)
HOST_UID="${HOST_UID:-1000}"
HOST_GID="${HOST_GID:-1000}"

if [ "$HOST_UID" = "0" ]; then
    echo -e "  ${YELLOW}[SKIP]${NC} Running as root on host — chown not required."
else
    # chown all scaffolded files back to the host user
    chown -R "${HOST_UID}:${HOST_GID}" . 2>/dev/null || {
        echo -e "  ${YELLOW}[WARN]${NC} chown failed — you may need to run: sudo chown -R \$(id -u):\$(id -g) ./app"
    }
    echo -e "  ${GREEN}[OK]${NC}   Ownership set to ${HOST_UID}:${HOST_GID} for all generated files."
fi

echo ""

# ── STEP 5: Final summary ──────────────────────────────────────────────────────
echo -e "${GREEN}${BOLD}============================================================${NC}"
echo -e "${GREEN}${BOLD}  Scaffolding Complete${NC}"
echo -e "${GREEN}${BOLD}  Project  : ${PROJECT_NAME}/${NC}"
echo -e "${GREEN}${BOLD}  Created  : ${CREATED_COUNT} domain app(s)${NC}"
echo -e "${GREEN}${BOLD}  Skipped  : ${SKIPPED_COUNT} (already existed)${NC}"
echo -e "${GREEN}${BOLD}============================================================${NC}"
echo ""
echo -e "${CYAN}NEXT STEPS:${NC}"
echo -e "  1. Add all domain apps to INSTALLED_APPS in darasa_project/settings.py"
echo -e "  2. Configure django-tenants SHARED_APPS and TENANT_APPS (Phase 4)"
echo -e "  3. Run: make migrate"
echo ""
