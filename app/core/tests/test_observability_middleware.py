from __future__ import annotations

import re
from typing import Any

import pytest
import structlog
from django.http import HttpResponse
from django.test import RequestFactory

from core.metrics import REGISTRY
from core.middleware import (
    REQUEST_ID_RESPONSE_HEADER,
    RequestObservabilityMiddleware,
    SecurityHeadersMiddleware,
)


UUID_HEX_PATTERN = re.compile(r"^[0-9a-f]{32}$")


@pytest.fixture(autouse=True)
def _clear_structlog_context():
    structlog.contextvars.clear_contextvars()
    yield
    structlog.contextvars.clear_contextvars()


def _build_request(factory: RequestFactory, **meta: Any):
    request = factory.get("/api/health/", **meta)
    request.tenant = None
    return request


class TestRequestObservabilityMiddleware:
    def test_generates_request_id_when_absent(self):
        middleware = RequestObservabilityMiddleware(lambda req: HttpResponse())
        request = _build_request(RequestFactory())

        response = middleware(request)

        request_id = response[REQUEST_ID_RESPONSE_HEADER]
        assert UUID_HEX_PATTERN.match(request_id)

    def test_propagates_inbound_request_id(self):
        middleware = RequestObservabilityMiddleware(lambda req: HttpResponse())
        request = _build_request(
            RequestFactory(), HTTP_X_REQUEST_ID="caller-supplied-id-123"
        )

        response = middleware(request)

        assert response[REQUEST_ID_RESPONSE_HEADER] == "caller-supplied-id-123"

    def test_binds_and_clears_context_during_request(self):
        observed_context: dict[str, Any] = {}

        def get_response(request):
            observed_context.update(structlog.contextvars.get_contextvars())
            return HttpResponse()

        middleware = RequestObservabilityMiddleware(get_response)
        request = _build_request(RequestFactory())

        middleware(request)

        assert observed_context["http_method"] == "GET"
        assert observed_context["http_path"] == "/api/health/"
        assert structlog.contextvars.get_contextvars() == {}

    def test_clears_context_even_when_view_raises(self):
        def get_response(request):
            raise RuntimeError("boom")

        middleware = RequestObservabilityMiddleware(get_response)
        request = _build_request(RequestFactory())

        with pytest.raises(RuntimeError):
            middleware(request)

        assert structlog.contextvars.get_contextvars() == {}

    def test_records_prometheus_metric_for_successful_request(self):
        middleware = RequestObservabilityMiddleware(
            lambda req: HttpResponse(status=204)
        )
        request = _build_request(RequestFactory())

        before = REGISTRY.get_sample_value(
            "darasa_http_requests_total",
            labels={"method": "GET", "status_code": "204"},
        ) or 0

        middleware(request)

        after = REGISTRY.get_sample_value(
            "darasa_http_requests_total",
            labels={"method": "GET", "status_code": "204"},
        )
        assert after is not None
        assert after >= before + 1


class TestSecurityHeadersMiddleware:
    def test_adds_csp_header_for_api_paths(self):
        middleware = SecurityHeadersMiddleware(lambda req: HttpResponse())
        request = RequestFactory().get("/api/health/")

        response = middleware(request)

        assert "default-src 'none'" in response["Content-Security-Policy"]
        assert response["Cross-Origin-Resource-Policy"] == "same-origin"
        assert "geolocation=()" in response["Permissions-Policy"]

    def test_skips_csp_header_outside_api_paths(self):
        middleware = SecurityHeadersMiddleware(lambda req: HttpResponse())
        request = RequestFactory().get("/admin/login/")

        response = middleware(request)

        assert "Content-Security-Policy" not in response

    def test_does_not_override_existing_header(self):
        def get_response(request):
            response = HttpResponse()
            response["Content-Security-Policy"] = "default-src 'self'"
            return response

        middleware = SecurityHeadersMiddleware(get_response)
        request = RequestFactory().get("/api/health/")

        response = middleware(request)

        assert response["Content-Security-Policy"] == "default-src 'self'"
