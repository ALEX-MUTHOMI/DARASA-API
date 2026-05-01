# =============================================================================
# Darasa-Core — Production Dockerfile
# Back To Front Development
#
# BUILD STRATEGY: Single Dockerfile, two modes.
#   Development:  docker compose up         (DEV=true  → installs dev deps)
#   Production:   docker compose -f docker-compose-deploy.yml up
#                                            (DEV=false → minimal runtime)
#
# SECURITY HARDENING:
#   - Non-root user (django-user UID/GID is build-arg configurable for Docker
#     Desktop on Linux/Mac — default 1000 matches most CI runners)
#   - No SUID binaries in the final layer
#   - Build tools are purged after installation
#   - PYTHONDONTWRITEBYTECODE prevents leftover .pyc files in the image layer
#   - PYTHONUNBUFFERED guarantees logs stream to Docker without buffering
# =============================================================================

FROM python:3.11-slim-bookworm AS base

LABEL maintainer="Back To Front Development <dev@backtofrontdev.io>"
LABEL org.opencontainers.image.title="darasa-core"
LABEL org.opencontainers.image.description="CBC Educational ERP — Kenyan Senior Secondary"

# ── Environment Flags ─────────────────────────────────────────────────────────
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # Poetry: disable venv creation inside the container (we use the system Python)
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_CACHE_DIR=/tmp/poetry_cache \
    PATH="/scripts:/py/bin:$PATH"

# ── Build Arguments ───────────────────────────────────────────────────────────
# DEV=true installs the [dev] dependency group (pytest, flake8, mutmut, etc.)
# APP_UID / APP_GID allow overriding UID to match the host user on Linux
ARG DEV=false
ARG APP_UID=1000
ARG APP_GID=1000

# =============================================================================
# LAYER 1: System dependencies (cached unless apt packages change)
# =============================================================================
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        # PostgreSQL client — pg_isready, psql for health-check scripts
        postgresql-client \
        # Required at runtime by psycopg2-binary
        libpq5 \
        # Required at runtime by Pillow
        libjpeg62-turbo \
        libwebp7 \
        # Build tools — purged after pip/poetry install (see below)
        build-essential \
        libpq-dev \
        zlib1g-dev \
        libjpeg-dev \
        libwebp-dev \
        # curl for Toxiproxy health-checks inside container if needed
        curl \
    && rm -rf /var/lib/apt/lists/*

# =============================================================================
# LAYER 2: Python virtual environment creation
# =============================================================================
RUN python -m venv /py && \
    /py/bin/pip install --upgrade pip==24.0 && \
    /py/bin/pip install poetry==1.8.3

# =============================================================================
# LAYER 3: Dependency installation (cached unless pyproject.toml/poetry.lock changes)
#
# CACHE SHIELD: We copy ONLY the lock files first. This guarantees the heavy
# `poetry install` layer is re-used on every code change (views, models, etc.)
# and only invalidated when dependencies actually change.
# =============================================================================
COPY pyproject.toml poetry.lock* /tmp/darasa/
WORKDIR /tmp/darasa

RUN if [ "$DEV" = "true" ]; then \
        /py/bin/poetry install --no-root --with dev; \
    else \
        /py/bin/poetry install --no-root --without dev; \
    fi && \
    # Purge build-time compilers to shrink the final image layer
    apt-get purge -y --auto-remove build-essential libpq-dev zlib1g-dev libjpeg-dev libwebp-dev && \
    rm -rf /var/lib/apt/lists/* /tmp/poetry_cache

# =============================================================================
# LAYER 4: Runtime user & directory structure
# =============================================================================
RUN groupadd --gid "${APP_GID}" django-user && \
    useradd \
        --uid "${APP_UID}" \
        --gid "${APP_GID}" \
        --create-home \
        --shell /usr/sbin/nologin \
        django-user && \
    # Static / media volume mount points
    mkdir -p /vol/web/media /vol/web/static /home/django-user && \
    chown -R django-user:django-user /vol /home/django-user && \
    chmod -R 755 /vol

# =============================================================================
# LAYER 5: Copy scripts (entrypoints) — changes here don't bust dep cache
# =============================================================================
COPY --chown=django-user:django-user ./scripts /scripts
RUN chmod -R +x /scripts

# =============================================================================
# LAYER 6: Copy application code LAST
#
# Rationale: editing models.py only busts this layer, not the heavy layers above.
# =============================================================================
COPY --chown=django-user:django-user ./app /app
WORKDIR /app

EXPOSE 8000
ENV HOME="/home/django-user"

# ── Drop Privileges ───────────────────────────────────────────────────────────
USER django-user

# ── Default entrypoint — overridden by docker-compose services ────────────────
CMD ["run.sh"]
