# syntax=docker/dockerfile:1.7

# Pinned by digest (not just tag) so the base image is immutable and cannot
# be silently swapped upstream (OWASP CICD-SEC-9: Improper Artifact Integrity
# Validation). Digest verified against the `python:3.11-slim-bookworm` tag on
# 2026-07-03; Dependabot's "docker" ecosystem entry in
# .github/dependabot.yml keeps this current going forward.
FROM python:3.14-slim-bookworm@sha256:4ff4b92a68355dbdb52584ab3391dff8d371a61d4e063468bfd0130e3189c6d9 AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_VERSION=2.3.4 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:/scripts:${PATH}"

FROM base AS builder

ARG POETRY_INSTALL_ARGS="--only main"

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv \
    && python -m venv /opt/poetry \
    && /opt/venv/bin/pip install --upgrade pip setuptools wheel \
    && /opt/poetry/bin/pip install "poetry==${POETRY_VERSION}"

WORKDIR /build
COPY pyproject.toml poetry.lock* ./

RUN VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:/opt/poetry/bin:${PATH}" \
    poetry install --no-root ${POETRY_INSTALL_ARGS}

FROM base AS runtime

ARG APP_UID=1000
ARG APP_GID=1000

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        curl \
        libpq5 \
        netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid "${APP_GID}" darasa \
    && useradd --uid "${APP_UID}" --gid "${APP_GID}" --create-home --shell /usr/sbin/nologin darasa \
    && mkdir -p /app /scripts /vol/web/static /vol/web/media /tmp/prometheus \
    && chown -R darasa:darasa /app /scripts /vol /tmp/prometheus

COPY --from=builder /opt/venv /opt/venv
COPY --chown=darasa:darasa ./scripts /scripts
COPY --chown=darasa:darasa ./app /app

WORKDIR /app

EXPOSE 8000

USER darasa

# Container-level liveness check. /api/health/ is answered by
# core.middleware.HealthCheckBypassMiddleware *before* tenant resolution, so
# it works regardless of Host header — exactly what an orchestrator's
# health probe needs, since it has no reason to know a specific tenant's
# domain. This does not replace real uptime/synthetic monitoring in a
# deployed environment (see docs/OBSERVABILITY.md); it only answers "is the
# process inside this container alive," which Dependabot has no bearing on
# whatsoever (see docs/OBSERVABILITY.md for that distinction too).
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://127.0.0.1:8000/api/health/ || exit 1

CMD ["bash", "/scripts/run.sh"]
