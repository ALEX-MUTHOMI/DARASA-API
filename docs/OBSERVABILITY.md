# Darasa-Core Observability

`structlog`, `opentelemetry-*`, and `prometheus-client` were declared in
`pyproject.toml` from early on but had zero call sites anywhere in the
codebase — the observability story was dependency-only. This document
describes what is now actually wired, and what remains backlog.

## What Is Real Today

### Structured logging

`core/observability.py` configures `structlog` once, at settings import
time, and routes it through Django's standard `LOGGING` dict via
`structlog.stdlib.ProcessorFormatter` (see `build_structlog_formatters` and
the `structlog` formatter entry in `darasa_project/settings.py`). This means:

- Every `structlog.get_logger(...)` call emits **structured** events (JSON in
  production/CI, readable key=value console output when `DEBUG=1`).
- Plain stdlib `logging.getLogger(...)` calls elsewhere in Django/third-party
  code are unaffected in shape, but share the same handler configuration.
- Log fields are consistent: `timestamp`, `level`, `logger`, `event`, plus
  whatever request-scoped context is bound (see below).

### Request correlation

`core.middleware.RequestObservabilityMiddleware` runs immediately after
`TenantMainMiddleware` (so `request.tenant` is already resolved) and, for the
lifetime of one request:

- Generates or propagates a request id (`X-Request-ID` request header in,
  same header echoed out on the response) so a client, a load balancer log,
  and an application log line can all be correlated to the same request.
- Binds `request_id`, `tenant_schema`, `http_method`, and `http_path` into
  `structlog.contextvars` so every log line emitted anywhere while handling
  that request — in a view, a service function, a signal handler — carries
  those fields automatically, with no call site changes required.
- Emits one structured `http.request.completed` (or
  `http.request.unhandled_exception`) summary log line per request, including
  status code, duration in milliseconds, and the authenticated actor id when
  available.
- Clears context in a `finally`-equivalent path so fields never leak into the
  next request handled by the same worker thread/greenlet.

### Application metrics

`core/metrics.py` defines real Prometheus collectors:

- `darasa_http_requests_total{method,status_code}` — request counter.
- `darasa_http_request_duration_seconds{method,status_code}` — latency
  histogram.
- `darasa_security_events_total{event_type}` — security-relevant event
  counter (rate limiting, unauthorized metrics access, etc.).

`RequestObservabilityMiddleware` records the first two on every request.
`core.security_events.log_security_event(...)` records the third and emits a
structured `security.event` log line in the same call, so every security
signal is visible in both logs and metrics without two call sites to keep in
sync.

`/api/observability/metrics/` exposes these in Prometheus text format,
**fail-closed by default**: it is only reachable without a token in
`DEBUG`/`TESTING`. In any other environment, `METRICS_ACCESS_TOKEN` must be
set and the caller must send a matching `X-Metrics-Token` header, or the
endpoint returns a plain **404** (not 401/403) so an anonymous scanner cannot
even confirm the endpoint exists.

### Distributed tracing (disabled by default, on purpose)

`.env.example` already anticipated `OTEL_TRACES_EXPORTER=none`; nothing ever
read it. `core/tracing.py` now does: `CoreConfig.ready()` calls
`configure_tracing(traces_exporter=..., service_name=...)`, which:

- Does nothing (and imports nothing OpenTelemetry-related) when the exporter
  is unset or `"none"` — the safe default for local dev, CI, and any
  environment without a collector.
- Only when an operator sets a real exporter value does it instrument
  Django and psycopg and start exporting spans via OTLP/gRPC.
- Never raises: a missing dependency or unreachable collector logs a
  structured warning and leaves the app fully functional rather than
  crashing startup.

### API documentation

`drf-spectacular` was installed but never wired to a URL. `/api/schema/`,
`/api/docs/` (Swagger UI), and `/api/redoc/` are now real, and reflect the
actual current HTTP surface (see `docs/API_DOCUMENTATION.md` for why that
surface is intentionally small today). Outside `DEBUG`, the schema/docs views
require an authenticated staff user (`SPECTACULAR_SETTINGS["SERVE_PERMISSIONS"]`)
so full route/shape metadata is not handed to anonymous callers in
production.

### Security headers

`core.middleware.SecurityHeadersMiddleware` adds `Content-Security-Policy`,
`Permissions-Policy`, `Cross-Origin-Resource-Policy`, and
`Cross-Origin-Opener-Policy` to every `/api/` response (scoped away from the
Django admin HTML pages, which need different, less restrictive policies to
function). It never overwrites a header a view already set explicitly.

### Rate limiting (first real endpoint)

The only real public, unauthenticated endpoint, `ParentPortalLoginView`, now
carries a dedicated DRF throttle scope (`parent_login`, default `5/min`,
IP-scoped) via `core.throttling.ParentLoginRateThrottle`. Every login attempt
and every throttled attempt logs a structured, PII-minimized security event
(a truncated HMAC fingerprint of the admission number, never the raw value).

## What Is Still Backlog

This closes the *application-layer* half of `OBS-P0-001` (structured logs)
and `OBS-P0-003` (application metrics) in
`docs/PRODUCTION_READINESS_BACKLOG.md`. It does **not** close:

- Shipping logs/metrics to an external aggregation platform, dashboards, or
  alerting (`OBS-P1-004` through `OBS-P1-008`) — that requires infrastructure
  this repository does not provision.
- `OBS-P0-002` audit logs for CCT/grading/admin/export actions — this pass
  only covers HTTP-request-level and the one real security-sensitive
  endpoint that exists today.
- Global/tenant-aware rate limiting beyond the one endpoint that currently
  exists (`SEC-P0-002`); there is no other public HTTP surface yet to rate
  limit.
- WAF/DDoS protection (`SEC-P0-001`) — edge infrastructure, not
  application code.
- Full CSP hardening for the Django admin UI itself, or a
  `Strict-Transport-Security` policy review beyond the existing
  `SECURE_HSTS_*` settings.

See `docs/adr/0004-observability-wiring.md` for the reasoning behind these
choices.
