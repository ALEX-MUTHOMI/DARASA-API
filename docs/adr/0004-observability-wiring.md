# ADR 0004: Observability wiring — structured logs, metrics, disabled-by-default tracing

## Status

Accepted. `structlog`, `prometheus-client`, and `opentelemetry-*` were
declared dependencies with zero call sites before this change; see
`docs/OBSERVABILITY.md` for the full picture of what is wired now.

## Context

Production readiness requires structured logs, application metrics, and
tracing (`OBS-P0-001`, `OBS-P0-003`, and related items in
`docs/PRODUCTION_READINESS_BACKLOG.md`). This repository already listed the
right dependencies (a correct forward-looking decision) but never wrote the
integration code, and `.env.example` already anticipated
`OTEL_TRACES_EXPORTER=none`/`OTEL_METRICS_EXPORTER=none` without anything
reading those variables.

## Decision

1. **Structured logging is always on**, JSON in non-DEBUG environments,
   readable console output locally, via `structlog` routed through Django's
   existing `LOGGING` dict (`core/observability.py`). This has no
   infrastructure dependency and no reason to be optional.
2. **Request correlation is always on**: every request gets a request id,
   and tenant/method/path/actor context is bound for the request's lifetime
   (`core/middleware.py`). Also no infrastructure dependency.
3. **Prometheus metrics are always collected in-process**, but the
   `/api/observability/metrics/` endpoint is **fail-closed by default**
   outside `DEBUG`/`TESTING` — an operator must explicitly configure
   `METRICS_ACCESS_TOKEN` to read them (`core/metrics.py`). Metrics
   endpoints reveal route/traffic shape and must not be an open
   reconnaissance surface.
4. **Distributed tracing stays disabled by default** (`core/tracing.py`,
   `CoreConfig.ready()`). Only an explicit non-`"none"` `OTEL_TRACES_EXPORTER`
   enables real OpenTelemetry instrumentation and OTLP export. A missing
   collector or missing optional dependency must degrade to "tracing off"
   with a logged warning, never a crashed application.

## Consequences

- Decisions 1 and 2 have no environment prerequisite: they work identically
  in this sandbox, in CI, and in a real deployment, because they never touch
  the network.
- Decision 3 means the metrics *endpoint* still needs an operator-provided
  secret in any real environment; without one, metrics are collected but
  unreachable — a deliberate "safe by default, useful once configured"
  trade-off over "on by default, secure later."
- Decision 4 means the CI/test environment (and, currently, this sandbox
  environment, which has no OTLP collector reachable) never attempts a
  network connection during tracing setup, so tests remain deterministic and
  offline-safe.
- None of this closes the full observability backlog: external log
  aggregation, dashboards, alerting, SLOs, and domain-specific metrics
  (`OBS-P1-004` through `OBS-P1-008`) still require infrastructure this
  repository does not provision. See `docs/OBSERVABILITY.md` for the exact
  boundary.
