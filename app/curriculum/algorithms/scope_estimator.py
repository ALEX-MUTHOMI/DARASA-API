from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from django.core.exceptions import ValidationError

from curriculum.algorithms.pii_guard import validate_governance_text


ALLOWED_SCOPE_KEYS = frozenset(
    {
        "scope_type",
        "country",
        "region",
        "county",
        "sub_county",
        "school_category",
        "senior_school_pathway",
        "grade_level",
        "learning_area",
        "strand",
        "sub_strand",
        "topic",
        "rubric",
        "exam_cycle",
        "teacher_training_cohort",
    }
)


def estimate_scope(claimed_scope: Mapping[str, Any] | None) -> dict[str, Any]:
    if not claimed_scope:
        return {"scope_type": "scope_unknown"}
    normalized: dict[str, Any] = {}
    for key, value in claimed_scope.items():
        key_text = str(key).strip().lower()
        if key_text not in ALLOWED_SCOPE_KEYS:
            raise ValidationError({"claimed_scope": "Scope dimension is not allowed."})
        if isinstance(value, str):
            validate_governance_text(value)
            normalized[key_text] = value.strip()
        elif isinstance(value, (int, bool)) or value is None:
            normalized[key_text] = value
        else:
            raise ValidationError({"claimed_scope": "Scope value is not allowed."})
    normalized.setdefault("scope_type", "scoped")
    return normalized
