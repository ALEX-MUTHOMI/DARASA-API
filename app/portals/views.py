from __future__ import annotations

from time import perf_counter, sleep

from django.conf import settings
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from portals.services import send_parent_login_code_request


GENERIC_PARENT_LOGIN_MESSAGE = "If this admission number exists, a code was sent."
PARENT_LOGIN_RESPONSE_FLOOR_SECONDS = getattr(
    settings,
    "PARENT_LOGIN_RESPONSE_FLOOR_SECONDS",
    0.15,
)


def _enforce_response_floor(started_at: float) -> None:
    elapsed = perf_counter() - started_at
    remaining = PARENT_LOGIN_RESPONSE_FLOOR_SECONDS - elapsed
    if remaining > 0:
        sleep(remaining)


class ParentPortalLoginView(APIView):
    authentication_classes: list[str] = []
    permission_classes = [AllowAny]

    def post(self, request):
        started_at = perf_counter()
        admission_number = str(request.data.get("admission_number", "")).strip()

        try:
            send_parent_login_code_request(admission_number)
        finally:
            _enforce_response_floor(started_at)

        return Response(
            {"detail": GENERIC_PARENT_LOGIN_MESSAGE},
            status=status.HTTP_202_ACCEPTED,
        )
