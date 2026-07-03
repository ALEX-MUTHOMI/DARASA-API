from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory

from core.throttling import ParentLoginRateThrottle
from portals.views import ParentPortalLoginView


pytestmark = [pytest.mark.security]


def _post_login(admission_number: str) -> Any:
    view = ParentPortalLoginView.as_view()
    request = APIRequestFactory().post(
        "/api/portals/parent/login/",
        {"admission_number": admission_number},
        format="json",
    )
    response = view(request)
    response.render()
    return response


def test_generic_response_regardless_of_admission_number():
    response = _post_login("ANYTHING-123")

    assert response.status_code == status.HTTP_202_ACCEPTED
    assert response.data == {
        "detail": "If this admission number exists, a code was sent."
    }


def test_missing_admission_number_still_returns_generic_response():
    response = _post_login("")

    assert response.status_code == status.HTTP_202_ACCEPTED


def test_logs_security_event_without_leaking_raw_admission_number():
    with patch("portals.views.log_security_event") as mock_log:
        _post_login("LEARNER-SECRET-42")

    request_event_calls = [
        call
        for call in mock_log.call_args_list
        if call.args[0] == "parent_login_requested"
    ]
    assert len(request_event_calls) == 1
    logged_fields = request_event_calls[0].kwargs
    assert "admission_fingerprint" in logged_fields
    assert "LEARNER-SECRET-42" not in str(logged_fields)


def test_rate_limit_blocks_after_threshold(monkeypatch):
    # DRF throttle classes freeze `THROTTLE_RATES` from
    # `settings.REST_FRAMEWORK` at class-import time, so
    # `django.test.override_settings` cannot retarget an already-imported
    # throttle class; patch the class attribute directly instead.
    monkeypatch.setattr(
        ParentLoginRateThrottle, "THROTTLE_RATES", {"parent_login": "3/min"}
    )

    responses = [_post_login("X") for _ in range(3)]
    for response in responses:
        assert response.status_code == status.HTTP_202_ACCEPTED

    throttled_response = _post_login("X")
    assert throttled_response.status_code == status.HTTP_429_TOO_MANY_REQUESTS


def test_rate_limited_request_logs_security_event(monkeypatch):
    monkeypatch.setattr(
        ParentLoginRateThrottle, "THROTTLE_RATES", {"parent_login": "1/min"}
    )

    _post_login("X")

    with patch("portals.views.log_security_event") as mock_log:
        _post_login("X")

    event_types = [call.args[0] for call in mock_log.call_args_list]
    assert "parent_login_rate_limited" in event_types
