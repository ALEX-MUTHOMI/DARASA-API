# syntax=docker/dockerfile:1.7

FROM python:3.11-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_VERSION=1.8.3 \
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
    && pip install --upgrade pip setuptools wheel \
    && pip install "poetry==${POETRY_VERSION}"

WORKDIR /build
COPY pyproject.toml poetry.lock* ./

RUN poetry install --no-root ${POETRY_INSTALL_ARGS}

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

CMD ["bash", "/scripts/run.sh"]
