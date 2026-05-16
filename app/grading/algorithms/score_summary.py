"""Build deterministic score summaries from official grade records."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any


def percentage(score: Decimal, max_score: Decimal) -> Decimal:
    if max_score <= 0:
        return Decimal("0.00")
    return ((score / max_score) * Decimal("100")).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )


def build_score_summary(*, grade_record: Any, assessment: Any) -> dict[str, Any]:
    score = grade_record.raw_score
    maximum = assessment.max_score
    return {
        "raw_score": str(score),
        "normalized_score": (
            str(grade_record.normalized_score)
            if grade_record.normalized_score is not None
            else None
        ),
        "max_score": str(maximum),
        "percentage": str(percentage(score, maximum)),
    }
