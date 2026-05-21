from __future__ import annotations

from decimal import Decimal
from typing import Any


def detect_weak_subjects(
    aggregates: list[dict[str, Any]],
    *,
    threshold: Decimal = Decimal("50.00"),
) -> list[dict[str, Any]]:
    weak = []
    for aggregate in aggregates:
        metrics = aggregate.get("metrics", {})
        mean = Decimal(str(metrics.get("mean_percentage", "0")))
        if mean < threshold:
            weak.append(
                {
                    "learning_area_id": str(aggregate.get("learning_area_id", "")),
                    "mean_percentage": str(mean.quantize(Decimal("0.01"))),
                    "learner_count": int(metrics.get("learner_count", 0)),
                }
            )
    return sorted(
        weak,
        key=lambda item: (
            Decimal(item["mean_percentage"]),
            item["learning_area_id"],
        ),
    )
