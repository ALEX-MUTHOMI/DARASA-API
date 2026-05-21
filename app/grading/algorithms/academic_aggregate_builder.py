from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0.00")


def _quantize(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def build_performance_metrics(
    *,
    percentages: list[Any],
    minimum_group_size: int = 3,
) -> dict[str, Any]:
    values = [_decimal(value) for value in percentages]
    count = len(values)
    mean = sum(values) / Decimal(count) if count else Decimal("0.00")
    return {
        "learner_count": count,
        "mean_percentage": _quantize(mean),
        "highest_percentage": _quantize(max(values)) if values else "0.00",
        "lowest_percentage": _quantize(min(values)) if values else "0.00",
        "minimum_group_size": minimum_group_size,
        "min_group_size_met": count >= minimum_group_size,
    }


def build_scope_aggregate(
    *,
    scope_type: str,
    percentages: list[Any],
    readiness_risk_count: int = 0,
    correction_blocker_count: int = 0,
    cct_blocker_count: int = 0,
    schema_mismatch_count: int = 0,
    minimum_group_size: int = 3,
) -> dict[str, Any]:
    metrics = build_performance_metrics(
        percentages=percentages,
        minimum_group_size=minimum_group_size,
    )
    metrics.update(
        {
            "scope_type": scope_type,
            "readiness_risk_count": readiness_risk_count,
            "correction_blocker_count": correction_blocker_count,
            "cct_blocker_count": cct_blocker_count,
            "schema_mismatch_count": schema_mismatch_count,
        }
    )
    return metrics
