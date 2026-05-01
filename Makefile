# ─────────────────────────────────────────────────────────────────────────────
# Makefile — Darasa-Core ERP
# Back To Front Development
#
# All commands run through Docker Compose — no local django-admin ever.
# DETERMINISM FIRST: the Docker environment is the only valid runtime.
# ─────────────────────────────────────────────────────────────────────────────

.PHONY: help build up down logs shell \
        scaffold purge \
        migrate makemigrations createsuperuser \
        test-unit test-integration test-security test-chaos \
        test-celery test-mutation test-coverage test-flake8 test-all

# Capture host UID/GID for the Docker permission fix in scaffold scripts.
# These are injected into the container so chown can restore ownership
# of Django-generated files back to the host user (prevents root-locked files).
HOST_UID := $(shell id -u)
HOST_GID := $(shell id -g)

# ── Default target ────────────────────────────────────────────────────────────
help:
	@echo ""
	@echo "  Darasa-Core — Available Commands"
	@echo "  ─────────────────────────────────────────────────────────"
	@echo "  Infrastructure:"
	@echo "    make build           — Build all Docker images"
	@echo "    make up              — Start the full dev stack"
	@echo "    make down            — Tear down the stack + volumes"
	@echo "    make logs            — Tail all service logs"
	@echo "    make shell           — Open a shell inside the app container"
	@echo ""
	@echo "  Migrations:"
	@echo "    make migrate         — Run shared schema migrations"
	@echo "    make makemigrations  — Generate new migration files"
	@echo ""
	@echo "  Test Suites:"
	@echo "    make test-unit       — Pure unit tests (no DB, fast)"
	@echo "    make test-integration — DB + Redis integration tests"
	@echo "    make test-security   — IDOR / tenant isolation / JWT attacks"
	@echo "    make test-chaos      — Toxiproxy fault injection"
	@echo "    make test-celery     — Celery task pipeline"
	@echo "    make test-mutation   — mutmut mutation testing baseline"
	@echo "    make test-coverage   — Full suite + HTML coverage report"
	@echo "    make test-flake8     — Lint"
	@echo "    make test-all        — Everything"
	@echo ""


# ── Infrastructure ────────────────────────────────────────────────────────────
build:
	docker compose build --parallel

up:
	docker compose up

down:
	docker compose down -v --remove-orphans

logs:
	docker compose logs -f

shell:
	docker compose exec app /bin/sh


# ── Project Scaffolding ───────────────────────────────────────────────────────
#
# SCAFFOLD: Full bootstrap sequence (run once at project initialization).
#   1. Spins up an ephemeral app container (--rm = auto-removed after exit)
#   2. Injects HOST_UID / HOST_GID so chown restores ownership of generated files
#   3. Runs purge_legacy.sh then scaffold_domains.sh in sequence
#
# WHY -e HOST_UID / HOST_GID?
#   Django-generated files inside Docker are owned by root (UID 0).
#   Without injecting the host UID, the developer cannot edit the generated
#   files without sudo. scaffold_domains.sh uses these for the final chown step.
scaffold: build
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  Darasa-Core — Full Scaffold Sequence"
	@echo "  Phase: Purge Legacy → Initialize Project → Scaffold Domains"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	docker compose run --rm \
		-e HOST_UID=$(HOST_UID) \
		-e HOST_GID=$(HOST_GID) \
		app bash -c " \
			set -eo pipefail && \
			chmod +x /scripts/purge_legacy.sh /scripts/scaffold_domains.sh && \
			echo '[SCAFFOLD] Step 1/2: Purging legacy domains...' && \
			bash /scripts/purge_legacy.sh && \
			echo '[SCAFFOLD] Step 2/2: Scaffolding Darasa-Core domains...' && \
			bash /scripts/scaffold_domains.sh \
		"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  ✅ Scaffold complete. Next: make migrate"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# PURGE ONLY: remove legacy apps without scaffolding new ones
purge: build
	docker compose run --rm \
		-e HOST_UID=$(HOST_UID) \
		-e HOST_GID=$(HOST_GID) \
		app bash -c " \
			chmod +x /scripts/purge_legacy.sh && \
			bash /scripts/purge_legacy.sh \
		"


# ── Database ──────────────────────────────────────────────────────────────────
migrate:
	docker compose run --rm app python manage.py migrate_schemas --shared --no-input

makemigrations:
	docker compose run --rm app python manage.py makemigrations $(filter-out $@,$(MAKECMDGOALS))

createsuperuser:
	docker compose run --rm app python manage.py createsuperuser


# ── Test Suites ───────────────────────────────────────────────────────────────
test-unit:
	docker compose run --rm test unit

test-integration:
	docker compose run --rm test integration

test-security:
	docker compose run --rm test security

test-chaos:
	docker compose run --rm test chaos

test-celery:
	docker compose run --rm test celery

test-mutation:
	docker compose run --rm test mutation

test-coverage:
	docker compose run --rm test coverage

test-flake8:
	docker compose run --rm test flake8

test-all:
	docker compose run --rm test all

# ── Utility ───────────────────────────────────────────────────────────────────
# Allow passing arguments to makemigrations without make errors
%:
	@:
