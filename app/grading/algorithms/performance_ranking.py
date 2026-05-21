from __future__ import annotations

from decimal import Decimal
from typing import Any


def rank_learners(
    items: list[dict[str, Any]],
    *,
    limit: int = 10,
) -> list[dict[str, Any]]:
    ordered = sorted(
        items,
        key=lambda item: (
            -Decimal(str(item.get("average_percentage", "0"))),
            str(item.get("student_id", "")),
        ),
    )
    return [
        {
            "student_id": str(item.get("student_id", "")),
            "rank": index + 1,
            "average_percentage": str(item.get("average_percentage", "0.00")),
        }
        for index, item in enumerate(ordered[:limit])
    ]
