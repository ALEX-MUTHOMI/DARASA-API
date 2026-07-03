"""Request observability and security-header middleware.

`RequestObservabilityMiddleware` binds correlation fields (request id, tenant
schema, actor id) to structlog's contextvars for the lifetime of a request so
every log line emitted anywhere while handling that request is automatically
tagged, then emits one structured summary log line and one Prometheus
observation per request.

`SecurityHeadersMiddleware` adds defense-in-depth headers that Django's
built-in `SecurityMiddleware` does not set (CSP, Permissions-Policy,
Cross-Origin-Resource-Policy) scoped to the JSON API surface so the (rarely
used) Django admin HTML pages are not affected.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable

import structlog
from django.http import HttpRequest, HttpResponse, JsonResponse

from core.metrics import record_http_request


REQUEST_ID_META_KEY = "HTTP_X_REQUEST_ID"
REQUEST_ID_RESPONSE_HEADER = "X-Request-ID"
MAX_INBOUND_REQUEST_ID_LENGTH = 128

request_logger = structlog.get_logger("darasa.request")


class HealthCheckBypassMiddleware:
    """Answers the liveness probe before tenant resolution can 404 it.

    `TenantMainMiddleware` resolves the active schema from the request's
    Host header against the `Domain` table; a host with no matching tenant
    domain 404s (see docs/security/ZAP_DAST_STRATEGY.md and ADR 0002). A
    container orchestrator's liveness/readiness probe, or an external
    uptime monitor, has no reason to know or send a specific tenant's Host
    header — it hits the container by IP or `localhost`. Without this
    bypass, `/api/health/` would 404 for exactly the callers who most need
    it to work, making Docker `HEALTHCHECK` / Kubernetes probes / uptime
    monitoring permanently report "unhealthy" regardless of actual app
    health. This must run *before* `TenantMainMiddleware` in `MIDDLEWARE`.
    """

    HEALTH_CHECK_PATH = "/api/health/"

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if request.path == self.HEALTH_CHECK_PATH:
            return JsonResponse({"healthy": True, "service": "darasa-core"})
        return self.get_response(request)


def _resolve_request_id(request: HttpRequest) -> str:
    inbound = request.META.get(REQUEST_ID_META_KEY, "")
    inbound = str(inbound).strip()[:MAX_INBOUND_REQUEST_ID_LENGTH]
    return inbound or uuid.uuid4().hex


class RequestObservabilityMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request_id = _resolve_request_id(request)
        tenant = getattr(request, "tenant", None)
        tenant_schema = getattr(tenant, "schema_name", None)

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            tenant_schema=tenant_schema,
            http_method=request.method,
            http_path=request.path,
        )

        started_at = time.monotonic()
        try:
            response = self.get_response(request)
        except Exception:
            duration_ms = round((time.monotonic() - started_at) * 1000, 2)
            request_logger.exception(
                "http.request.unhandled_exception", duration_ms=duration_ms
            )
            record_http_request(
                method=request.method or "UNKNOWN",
                status_code=500,
                duration_seconds=duration_ms / 1000,
            )
            structlog.contextvars.clear_contextvars()
            raise

        duration_ms = round((time.monotonic() - started_at) * 1000, 2)
        actor = getattr(request, "user", None)
        actor_is_authenticated = bool(getattr(actor, "is_authenticated", False))
        actor_id = getattr(actor, "id", None) if actor_is_authenticated else None

        is_error_response = response.status_code >= 400
        log_method = (
            request_logger.warning if is_error_response else request_logger.info
        )
        log_method(
            "http.request.completed",
            status_code=response.status_code,
            duration_ms=duration_ms,
            actor_id=actor_id,
        )
        record_http_request(
            method=request.method or "UNKNOWN",
            status_code=response.status_code,
            duration_seconds=duration_ms / 1000,
        )

        response[REQUEST_ID_RESPONSE_HEADER] = request_id
        structlog.contextvars.clear_contextvars()
        return response


class SecurityHeadersMiddleware:
    """Adds defense-in-depth headers Django's SecurityMiddleware omits.

    Verified against a real OWASP ZAP baseline scan (see
    docs/security/ZAP_DAST_STRATEGY.md), which caught two real gaps in an
    earlier version of this middleware: headers were only applied under
    `/api/` (missing the site root entirely), and a blanket
    `default-src 'none'` CSP would have silently broken the Swagger UI docs
    page, which loads its JS/CSS from a CDN. Both are fixed below.
    """

    # Django admin renders its own inline scripts/styles and Django's
    # staticfiles/whitenoise already set their own appropriate caching
    # headers; neither should be overridden by a blanket API-oriented policy.
    EXEMPT_PATH_PREFIXES = ("/admin/", "/static/", "/media/")

    # The Swagger UI page (only) needs to load JS/CSS from a CDN by default
    # (drf-spectacular has no bundled 'sidecar' assets installed). Allow
    # exactly that origin instead of exempting the page from CSP entirely.
    SWAGGER_UI_PATH_PREFIX = "/api/docs/"
    SWAGGER_UI_CDN_ORIGIN = "https://cdn.jsdelivr.net"

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)

        # Never advertise backend server/version details (WSGIServer/x.y in
        # dev, gunicorn/x.y in production) to a potential attacker.
        response["Server"] = "Darasa"

        if not request.path.startswith(self.EXEMPT_PATH_PREFIXES):
            if request.path.startswith(self.SWAGGER_UI_PATH_PREFIX):
                csp = (
                    f"default-src 'self'; "
                    f"script-src 'self' 'unsafe-inline' {self.SWAGGER_UI_CDN_ORIGIN}; "
                    f"style-src 'self' 'unsafe-inline' {self.SWAGGER_UI_CDN_ORIGIN}; "
                    f"img-src 'self' data: {self.SWAGGER_UI_CDN_ORIGIN}; "
                    f"connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"
                )
            else:
                # form-action and frame-ancestors deliberately do not fall
                # back to default-src per the CSP spec and must be listed
                # explicitly (ZAP CSP rule 10055 caught this omission).
                csp = (
                    "default-src 'none'; frame-ancestors 'none'; "
                    "form-action 'none'; base-uri 'none'"
                )
            response.setdefault("Content-Security-Policy", csp)
            response.setdefault("Cross-Origin-Resource-Policy", "same-origin")
            response.setdefault("Cross-Origin-Opener-Policy", "same-origin")
            response.setdefault(
                "Permissions-Policy",
                "geolocation=(), microphone=(), camera=(), payment=()",
            )
            response.setdefault("Cache-Control", "no-store")

        return response
