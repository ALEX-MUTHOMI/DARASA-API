from __future__ import annotations

from statistics import mean
from time import perf_counter
from typing import Any

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory

from portals.views import (
    GENERIC_PARENT_LOGIN_MESSAGE,
    ParentPortalLoginView,
)


def _invoke_parent_login(view, admission_number: str) -> tuple[Any, float]:
    request = APIRequestFactory().post(
        "/api/portals/parent/login/",
        {"admission_number": admission_number},
        format="json",
    )
    started_at = perf_counter()
    response: Any = view(request)
    response.render()
    duration = perf_counter() - started_at
    return response, duration


@pytest.mark.security
def test_parent_portal_login_masks_admission_number_existence(monkeypatch):
    def fake_send_parent_login_code_request(admission_number: str) -> bool:
        return admission_number == "ADM-VALID-001"

    monkeypatch.setattr(
        "portals.views.send_parent_login_code_request",
        fake_send_parent_login_code_request,
    )
    monkeypatch.setattr(
        "portals.views.PARENT_LOGIN_RESPONSE_FLOOR_SECONDS",
        0.01,
    )

    view = ParentPortalLoginView.as_view()

    valid_response, _ = _invoke_parent_login(view, "ADM-VALID-001")
    invalid_response, _ = _invoke_parent_login(view, "ADM-INVALID-404")

    assert (
        valid_response.status_code
        == invalid_response.status_code
        == status.HTTP_202_ACCEPTED
    )
    assert valid_response.data == invalid_response.data == {
        "detail": GENERIC_PARENT_LOGIN_MESSAGE,
    }


@pytest.mark.security
def test_parent_portal_login_enforces_timing_floor(monkeypatch):
    def fake_send_parent_login_code_request(admission_number: str) -> bool:
        return admission_number == "ADM-VALID-001"

    monkeypatch.setattr(
        "portals.views.send_parent_login_code_request",
        fake_send_parent_login_code_request,
    )
    monkeypatch.setattr(
        "portals.views.PARENT_LOGIN_RESPONSE_FLOOR_SECONDS",
        0.03,
    )

    view = ParentPortalLoginView.as_view()

    valid_durations = [
        _invoke_parent_login(view, "ADM-VALID-001")[1]
        for _ in range(5)
    ]
    invalid_durations = [
        _invoke_parent_login(view, "ADM-INVALID-404")[1]
        for _ in range(5)
    ]

    valid_mean = mean(valid_durations)
    invalid_mean = mean(invalid_durations)

    assert valid_mean >= 0.03
    assert invalid_mean >= 0.03
    assert abs(valid_mean - invalid_mean) <= 0.02
