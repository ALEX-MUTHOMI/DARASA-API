from __future__ import annotations

from decimal import Decimal
from typing import Any


def detect_most_improved(
    *,
    current: list[dict[str, Any]],
    previous: list[dict[str, Any]] | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    previous_map = {
        str(item.get("student_id")): Decimal(str(item.get("average_percentage", "0")))
        for item in previous or []
    }
    deltas = []
    for item in current:
        student_id = str(item.get("student_id"))
        current_average = Decimal(str(item.get("average_percentage", "0")))
        delta = current_average - previous_map.get(student_id, Decimal("0"))
        deltas.append(
            {
                "student_id": student_id,
                "delta": str(delta.quantize(Decimal("0.01"))),
                "average_percentage": str(current_average.quantize(Decimal("0.01"))),
            }
        )
    return sorted(
        deltas,
        key=lambda item: (-Decimal(item["delta"]), item["student_id"]),
    )[:limit]
