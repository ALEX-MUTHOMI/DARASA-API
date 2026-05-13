"""Curriculum publication workflow guard.

This module encodes the security boundary between "a change was detected" and
"a version became active."  Direct detected-to-published transitions are
forbidden so source registration, review, approval, and publication remain
auditable and separate.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError


ALLOWED_TRANSITIONS = {
    "detected": {"quarantined", "under_review", "rejected"},
    "quarantined": {"under_review", "rejected"},
    "under_review": {"approved", "rejected"},
    "approved": {"published", "rejected"},
    "published": {"superseded"},
    "rejected": set(),
    "superseded": set(),
}


def validate_transition(old_status: str, new_status: str) -> None:
    if new_status not in ALLOWED_TRANSITIONS.get(old_status, set()):
        raise ValidationError(
            {"status": "Curriculum workflow transition is not allowed."}
        )
