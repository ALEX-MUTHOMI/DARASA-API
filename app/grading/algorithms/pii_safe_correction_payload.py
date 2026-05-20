"""PII-safe text and event payload helpers for correction workflows."""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError


FORBIDDEN_EVENT_FIELDS = frozenset(
    {
        "raw_score",
        "old_mark",
        "new_mark",
        "old_value",
        "new_value",
        "learner_name",
        "guardian",
        "teacher_private_notes",
        "raw_grade_grid",
        "reason",
    }
)

UNSAFE_TEXT_TOKENS = frozenset({"<script", "<svg", "onerror", "javascript:"})


def sanitize_untrusted_text(value: Any, *, max_length: int = 180) -> str:
    text = str(value or "").strip()
    lowered = text.lower()
    if any(token in lowered for token in UNSAFE_TEXT_TOKENS):
        raise ValidationError({"text": "Correction text is unsafe."})
    return text[:max_length]


def assert_pii_safe_event_payload(payload: dict[str, Any]) -> None:
    forbidden = FORBIDDEN_EVENT_FIELDS & set(payload)
    if forbidden:
        raise ValidationError({"payload": "Correction event payload contains PII."})
