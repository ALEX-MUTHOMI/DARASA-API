"""Prometheus application metrics.

`prometheus-client` was already a declared dependency with zero call sites.
This module defines the actual counters/histograms and a fail-closed-by-
default `/api/observability/metrics/` view.

Hacker-first note: a metrics endpoint is itself an information-disclosure
surface (it reveals route cardinality, traffic shape, and can be used to
fingerprint deploys). It must not be publicly reachable without a shared
secret in any environment that is not DEBUG/TESTING, and an unauthorized
request returns 404 rather than 401/403 so it does not even confirm the
endpoint exists to an anonymous scanner.
"""

from __future__ import annotations

import hmac

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
)


REGISTRY = CollectorRegistry()

HTTP_REQUESTS_TOTAL = Counter(
    "darasa_http_requests_total",
    "Total HTTP requests processed, labeled by method and status code.",
    ["method", "status_code"],
    registry=REGISTRY,
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "darasa_http_request_duration_seconds",
    "HTTP request duration in seconds, labeled by method and status code.",
    ["method", "status_code"],
    registry=REGISTRY,
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)

SECURITY_EVENTS_TOTAL = Counter(
    "darasa_security_events_total",
    "Security-relevant events observed by the application, by event type.",
    ["event_type"],
    registry=REGISTRY,
)


def record_http_request(
    *, method: str, status_code: int, duration_seconds: float
) -> None:
    labels = {"method": method, "status_code": str(status_code)}
    HTTP_REQUESTS_TOTAL.labels(**labels).inc()
    HTTP_REQUEST_DURATION_SECONDS.labels(**labels).observe(duration_seconds)


def record_security_event(event_type: str) -> None:
    SECURITY_EVENTS_TOTAL.labels(event_type=event_type).inc()


def _metrics_access_is_authorized(request: HttpRequest) -> bool:
    configured_token = getattr(settings, "METRICS_ACCESS_TOKEN", "") or ""
    is_debug = bool(getattr(settings, "DEBUG", False))
    is_testing = bool(getattr(settings, "TESTING", False))
    dev_mode = is_debug or is_testing

    if not configured_token:
        # Fail closed outside DEBUG/TESTING: an unconfigured token must never
        # imply "open metrics", it must imply "no access".
        return dev_mode

    provided_token = request.META.get("HTTP_X_METRICS_TOKEN", "") or ""
    return hmac.compare_digest(provided_token, configured_token)


def metrics_view(request: HttpRequest) -> HttpResponse:
    if not _metrics_access_is_authorized(request):
        record_security_event("metrics_access_denied")
        return HttpResponse(status=404)
    return HttpResponse(generate_latest(REGISTRY), content_type=CONTENT_TYPE_LATEST)
