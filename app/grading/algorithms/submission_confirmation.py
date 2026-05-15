"""Step-up confirmation validation for final grade submission.

Final submission is the point of no silent overwrite.  These checks protect
shared-computer environments without storing raw passwords or PINs.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.core.exceptions import ValidationError
from django.utils import timezone


ALLOWED_CONFIRMATION_METHODS = frozenset(
    {"password_reauth", "teacher_pin", "session_step_up"}
)
CONFIRMATION_TTL_SECONDS = 300


def validate_confirmation(
    *,
    confirmation: dict[str, Any] | None,
    actor_id: Any,
    tenant_id: Any,
    now: Any | None = None,
) -> dict[str, Any]:
    if not isinstance(confirmation, dict):
        raise ValidationError({"confirmation": "Step-up confirmation is required."})
    if "password" in confirmation or "pin" in confirmation:
        raise ValidationError({"confirmation": "Raw credentials are not accepted."})
    method = str(confirmation.get("method", "")).strip()
    if method not in ALLOWED_CONFIRMATION_METHODS:
        raise ValidationError({"confirmation": "Confirmation method is invalid."})
    if str(confirmation.get("actor_id", "")) != str(actor_id):
        raise ValidationError({"confirmation": "Confirmation actor is invalid."})
    if str(confirmation.get("tenant_id", "")) != str(tenant_id):
        raise ValidationError({"confirmation": "Confirmation tenant is invalid."})
    confirmed_at = confirmation.get("confirmed_at")
    if confirmed_at is None:
        raise ValidationError({"confirmation": "Confirmation time is required."})
    current_time = now or timezone.now()
    if confirmed_at > current_time:
        raise ValidationError({"confirmation": "Confirmation time is invalid."})
    if current_time - confirmed_at > timedelta(seconds=CONFIRMATION_TTL_SECONDS):
        raise ValidationError({"confirmation": "Confirmation has expired."})
    reference = str(confirmation.get("confirmation_reference", "")).strip()
    if not reference:
        raise ValidationError(
            {"confirmation": "Confirmation reference is required."}
        )
    return {
        "method": method,
        "confirmed_at": confirmed_at,
        "confirmation_reference": reference,
    }
