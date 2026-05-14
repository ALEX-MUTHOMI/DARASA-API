"""Score bound validation for academic record integrity.

Models and future services call this helper so score validation is consistent
and testable without database access.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from django.core.exceptions import ValidationError


def to_decimal(value: Any, *, field_name: str) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError({field_name: "Score must be numeric."}) from exc


def validate_score_bounds(*, score: Any, max_score: Any) -> Decimal:
    maximum = to_decimal(max_score, field_name="max_score")
    if maximum <= 0:
        raise ValidationError({"max_score": "Maximum score must be positive."})
    value = to_decimal(score, field_name="raw_score")
    if value < 0:
        raise ValidationError({"raw_score": "Score cannot be negative."})
    if value > maximum:
        raise ValidationError({"raw_score": "Score cannot exceed maximum score."})
    return value
