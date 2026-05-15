"""Grid column construction for simple and component assessments."""

from __future__ import annotations

from decimal import Decimal
from typing import Any


def build_component_columns(components: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            "component_id": str(component.id),
            "name": component.name,
            "max_score": str(component.max_score),
            "is_required": component.is_required,
            "rubric_foundation_id": (
                str(component.rubric_foundation_id)
                if component.rubric_foundation_id
                else None
            ),
        }
        for component in sorted(components, key=lambda item: (item.order, item.name))
    ]


def component_total(component_scores: dict[str, Any]) -> Decimal:
    total = Decimal("0.00")
    for value in component_scores.values():
        total += Decimal(str(value))
    return total
