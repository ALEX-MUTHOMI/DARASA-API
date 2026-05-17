"""Notice batching helpers for national-scale curriculum governance."""

from __future__ import annotations

from dataclasses import dataclass

from django.core.exceptions import ValidationError


@dataclass(frozen=True)
class NoticeBatchPlan:
    total_count: int
    batch_size: int
    batch_count: int


def plan_notice_batch(
    *,
    total_count: int,
    batch_size: int,
) -> NoticeBatchPlan:
    if total_count < 0:
        raise ValidationError({"total_count": "Total notice count is invalid."})
    if batch_size < 1:
        raise ValidationError({"batch_size": "Batch size must be positive."})
    batch_count = (total_count + batch_size - 1) // batch_size
    return NoticeBatchPlan(
        total_count=total_count,
        batch_size=batch_size,
        batch_count=batch_count,
    )
