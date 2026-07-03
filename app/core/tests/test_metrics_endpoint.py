from __future__ import annotations

import pytest
from django.test import RequestFactory

from core.metrics import metrics_view


pytestmark = [pytest.mark.security]


def test_metrics_open_in_debug_when_no_token_configured(settings):
    settings.DEBUG = True
    settings.METRICS_ACCESS_TOKEN = ""

    response = metrics_view(RequestFactory().get("/api/observability/metrics/"))

    assert response.status_code == 200
    assert b"darasa_http_requests_total" in response.content


def test_metrics_closed_outside_debug_when_no_token_configured(settings):
    settings.DEBUG = False
    settings.TESTING = False
    settings.METRICS_ACCESS_TOKEN = ""

    response = metrics_view(RequestFactory().get("/api/observability/metrics/"))

    assert response.status_code == 404


def test_metrics_requires_matching_token_outside_debug(settings):
    settings.DEBUG = False
    settings.TESTING = False
    settings.METRICS_ACCESS_TOKEN = "correct-token"

    denied = metrics_view(RequestFactory().get("/api/observability/metrics/"))
    wrong_token = metrics_view(
        RequestFactory().get(
            "/api/observability/metrics/", HTTP_X_METRICS_TOKEN="wrong-token"
        )
    )
    allowed = metrics_view(
        RequestFactory().get(
            "/api/observability/metrics/", HTTP_X_METRICS_TOKEN="correct-token"
        )
    )

    assert denied.status_code == 404
    assert wrong_token.status_code == 404
    assert allowed.status_code == 200
    assert allowed["Content-Type"].startswith("text/plain")
