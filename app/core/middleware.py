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
from django.http import HttpRequest, HttpResponse

from core.metrics import record_http_request


REQUEST_ID_META_KEY = "HTTP_X_REQUEST_ID"
REQUEST_ID_RESPONSE_HEADER = "X-Request-ID"
MAX_INBOUND_REQUEST_ID_LENGTH = 128

request_logger = structlog.get_logger("darasa.request")


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
    """Adds defense-in-depth headers Django's SecurityMiddleware omits."""

    API_PATH_PREFIX = "/api/"

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        if request.path.startswith(self.API_PATH_PREFIX):
            response.setdefault(
                "Content-Security-Policy",
                "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
            )
            response.setdefault("Cross-Origin-Resource-Policy", "same-origin")
            response.setdefault("Cross-Origin-Opener-Policy", "same-origin")
            response.setdefault(
                "Permissions-Policy",
                "geolocation=(), microphone=(), camera=(), payment=()",
            )
        return response
