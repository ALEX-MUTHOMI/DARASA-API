from __future__ import annotations

import json
import re
from typing import Any

import pytest
import structlog
from django.http import HttpResponse
from django.test import RequestFactory

from core.metrics import REGISTRY
from core.middleware import (
    REQUEST_ID_RESPONSE_HEADER,
    HealthCheckBypassMiddleware,
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


class TestHealthCheckBypassMiddleware:
    def test_answers_health_check_without_calling_downstream(self):
        downstream_was_called = False

        def get_response(request):
            nonlocal downstream_was_called
            downstream_was_called = True
            return HttpResponse(status=404)

        middleware = HealthCheckBypassMiddleware(get_response)
        # No Host-header-matched tenant domain exists for this request, the
        # exact condition that otherwise makes TenantMainMiddleware 404 the
        # liveness probe every container orchestrator relies on.
        request = RequestFactory().get("/api/health/")

        response = middleware(request)

        assert downstream_was_called is False
        assert response.status_code == 200
        assert json.loads(response.content) == {
            "healthy": True,
            "service": "darasa-core",
        }

    def test_passes_through_non_health_check_paths(self):
        def get_response(request):
            return HttpResponse(status=404)

        middleware = HealthCheckBypassMiddleware(get_response)
        request = RequestFactory().get("/api/portals/parent/login/")

        response = middleware(request)

        assert response.status_code == 404


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
        assert response["Cache-Control"] == "no-store"

    def test_csp_explicitly_sets_form_action_and_frame_ancestors(self):
        # Regression test: form-action and frame-ancestors do not inherit
        # from default-src per the CSP spec and must be listed explicitly —
        # caught by ZAP CSP rule 10055 ("Failure to Define Directive with No
        # Fallback") during a real baseline scan.
        middleware = SecurityHeadersMiddleware(lambda req: HttpResponse())
        request = RequestFactory().get("/api/health/")

        response = middleware(request)

        csp = response["Content-Security-Policy"]
        assert "form-action 'none'" in csp
        assert "frame-ancestors 'none'" in csp

    def test_applies_csp_to_the_site_root_too(self):
        # Regression test: an earlier version of this middleware only
        # applied headers under /api/, leaving the root path (and any
        # future non-/api/ route) with no CSP at all — caught by a real
        # OWASP ZAP baseline scan. See docs/security/ZAP_DAST_STRATEGY.md.
        middleware = SecurityHeadersMiddleware(lambda req: HttpResponse())
        request = RequestFactory().get("/")

        response = middleware(request)

        assert "Content-Security-Policy" in response

    def test_skips_csp_header_for_admin_static_and_media_paths(self):
        middleware = SecurityHeadersMiddleware(lambda req: HttpResponse())
        for path in ("/admin/login/", "/static/app.css", "/media/upload.png"):
            response = middleware(RequestFactory().get(path))
            assert "Content-Security-Policy" not in response, path

    def test_swagger_ui_gets_cdn_scoped_csp_instead_of_default_none(self):
        # Regression test: a blanket 'default-src none' CSP would silently
        # break Swagger UI, which loads its JS/CSS from a CDN by default
        # (no drf-spectacular-sidecar package installed) — also caught by a
        # real ZAP-adjacent manual check while investigating the scan
        # results, not by ZAP itself.
        middleware = SecurityHeadersMiddleware(lambda req: HttpResponse())
        request = RequestFactory().get("/api/docs/")

        response = middleware(request)

        csp = response["Content-Security-Policy"]
        assert "default-src 'none'" not in csp
        assert "cdn.jsdelivr.net" in csp

    def test_overrides_server_header_to_avoid_version_leakage(self):
        # Regression test: ZAP flagged 'Server Leaks Version Information'
        # (WSGIServer/x.y CPython/x.y.z in dev; gunicorn/x.y in production).
        def get_response(request):
            response = HttpResponse()
            response["Server"] = "WSGIServer/0.2 CPython/3.11.15"
            return response

        middleware = SecurityHeadersMiddleware(get_response)
        request = RequestFactory().get("/api/health/")

        response = middleware(request)

        assert response["Server"] == "Darasa"

    def test_does_not_override_existing_csp_header(self):
        def get_response(request):
            response = HttpResponse()
            response["Content-Security-Policy"] = "default-src 'self'"
            return response

        middleware = SecurityHeadersMiddleware(get_response)
        request = RequestFactory().get("/api/health/")

        response = middleware(request)

        assert response["Content-Security-Policy"] == "default-src 'self'"
