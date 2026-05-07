SHELL := /usr/bin/env bash
.SHELLFLAGS := -eo pipefail -c

COMPOSE ?= docker compose
DJANGO_SERVICE ?= django
HOST_UID ?= $(shell id -u 2>/dev/null || echo 1000)
HOST_GID ?= $(shell id -g 2>/dev/null || echo 1000)

.PHONY: build up down logs migrate makemigrations test test-chaos lint security \
	scaffold purge shell django-check

build:
	$(COMPOSE) build

up:
	$(COMPOSE) up

down:
	$(COMPOSE) down --remove-orphans

logs:
	$(COMPOSE) logs -f

migrate:
	$(COMPOSE) run --rm $(DJANGO_SERVICE) bash -lc 'cd /workspace/app && python manage.py migrate'

makemigrations:
	$(COMPOSE) run --rm $(DJANGO_SERVICE) bash -lc 'cd /workspace/app && python manage.py makemigrations'

test:
	$(COMPOSE) run --rm $(DJANGO_SERVICE) bash /workspace/scripts/run-tests.sh unit

test-chaos:
	$(COMPOSE) run --rm $(DJANGO_SERVICE) bash /workspace/scripts/run-tests.sh chaos

lint:
	$(COMPOSE) run --rm $(DJANGO_SERVICE) bash -lc 'cd /workspace && poetry run flake8 app'

security:
	$(COMPOSE) run --rm $(DJANGO_SERVICE) bash -lc 'cd /workspace && poetry run bandit -r app -c pyproject.toml && poetry run pip-audit'

scaffold:
	$(COMPOSE) run --rm --user root \
		-e HOST_UID=$(HOST_UID) \
		-e HOST_GID=$(HOST_GID) \
		$(DJANGO_SERVICE) bash /workspace/scripts/scaffold_domains.sh

purge:
	$(COMPOSE) run --rm --user root $(DJANGO_SERVICE) bash /workspace/scripts/purge_legacy.sh

shell:
	$(COMPOSE) run --rm $(DJANGO_SERVICE) bash

django-check:
	$(COMPOSE) run --rm $(DJANGO_SERVICE) bash -lc 'cd /workspace/app && python manage.py check'
