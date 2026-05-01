#!/bin/bash
# =============================================================================
# purge_legacy.sh — Darasa-Core Legacy Domain Purge
# Back To Front Development
#
# PURPOSE:
#   Safely removes legacy PhotoBox application directories from the /app root.
#   This script is IDEMPOTENT — running it multiple times is always safe.
#   If a directory does not exist, it is logged and skipped.
#
# USAGE (via Makefile — DO NOT run outside Docker):
#   docker compose run --rm app bash /scripts/purge_legacy.sh
#
# FAIL-FAST: set -eo pipefail ensures any error halts execution immediately.
#   -e  : exit on any command failure
#   -o pipefail : treat pipe failures as errors (not just the last command)
# =============================================================================
set -eo pipefail

# ── Colour codes for readable CI output ──────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No colour

echo ""
echo -e "${CYAN}============================================================${NC}"
echo -e "${CYAN}  Darasa-Core — Legacy Domain Purge${NC}"
echo -e "${CYAN}  Working directory: $(pwd)${NC}"
echo -e "${CYAN}============================================================${NC}"
echo ""

# ── CONTRACT: This script must be run from inside the /app directory ─────────
# Design by Contract — assert we are in the right place before mutating state.
if [ ! -f "manage.py" ] && [ ! -d "darasa_project" ] && [ ! -d "app" ]; then
    echo -e "${RED}[ERROR] Cannot locate Django project root.${NC}"
    echo -e "${RED}        Expected to find manage.py or darasa_project/ in: $(pwd)${NC}"
    echo -e "${RED}        Run this script from /app inside the Docker container.${NC}"
    exit 1
fi

# ── Legacy domains to be purged ───────────────────────────────────────────────
# These are PhotoBox-era apps that have no place in Darasa-Core.
LEGACY_APPS=(
    "gallery"
    "billing"
    "checkout"
    "webhooks"
    "user"
    "cgi.py"
)

PURGED_COUNT=0
SKIPPED_COUNT=0

echo -e "${YELLOW}[INFO] Scanning for legacy application directories...${NC}"
echo ""

for app in "${LEGACY_APPS[@]}"; do
    if [ -e "$app" ]; then
        echo -e "  ${RED}[PURGE]${NC}  Found: ${app} — removing..."
        rm -rf "$app"

        # Verify the deletion actually succeeded (fail-fast guard)
        if [ -e "$app" ]; then
            echo -e "  ${RED}[ERROR]${NC}  Failed to remove: ${app}. Check file permissions."
            exit 1
        fi

        echo -e "  ${GREEN}[OK]${NC}     Removed: ${app}"
        PURGED_COUNT=$((PURGED_COUNT + 1))
    else
        echo -e "  ${YELLOW}[SKIP]${NC}   Not found: ${app} (already clean)"
        SKIPPED_COUNT=$((SKIPPED_COUNT + 1))
    fi
done

echo ""
echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN}  Purge Complete${NC}"
echo -e "${GREEN}  Removed : ${PURGED_COUNT} legacy domain(s)${NC}"
echo -e "${GREEN}  Skipped : ${SKIPPED_COUNT} (already absent)${NC}"
echo -e "${GREEN}============================================================${NC}"
echo ""
