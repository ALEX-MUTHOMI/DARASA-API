"""Draft row validation and optimistic merge decisions."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError

from grading.algorithms.batch_validation import validate_grade_rows


def validate_draft_version(
    *,
    current_version: int | None,
    expected_version: int | None,
) -> None:
    if expected_version is not None and current_version is not None:
        if int(expected_version) != int(current_version):
            raise ValidationError({"draft_version": "Draft version is stale."})


def normalize_draft_rows(
    *,
    rows: list[dict[str, Any]],
    roster_student_ids: set[str],
    max_score: Decimal,
    components: list[Any],
) -> list[dict[str, Any]]:
    return validate_grade_rows(
        rows=rows,
        roster_student_ids=roster_student_ids,
        max_score=max_score,
        components=components,
        require_complete=False,
    )
