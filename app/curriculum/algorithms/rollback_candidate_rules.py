from __future__ import annotations

from django.core.exceptions import ValidationError


ROLLBACK_STATUSES = frozenset(
    {
        "suspected",
        "quarantined",
        "under_review",
        "verified",
        "rejected",
        "rollback_planned",
        "withdrawn",
    }
)


def validate_rollback_candidate_status(status: str) -> str:
    normalized = status.strip().lower()
    if normalized not in ROLLBACK_STATUSES:
        raise ValidationError({"status": "Rollback candidate status is invalid."})
    return normalized
