"""Batch planning helpers for curriculum rollout and adoption work."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from math import ceil

from django.core.exceptions import ValidationError


@dataclass(frozen=True)
class RolloutBatch:
    batch_number: int
    start_index: int
    end_index: int


def validate_adoption_window(
    *,
    publication_effective_from: date,
    adoption_effective_from: date,
) -> None:
    if adoption_effective_from < publication_effective_from:
        raise ValidationError(
            {"effective_from": "Adoption cannot precede publication."}
        )


def plan_rollout_batches(
    *,
    total_items: int,
    batch_size: int,
) -> list[RolloutBatch]:
    if total_items < 0:
        raise ValidationError({"total_items": "Total item count is invalid."})
    if batch_size < 1:
        raise ValidationError({"batch_size": "Batch size must be positive."})
    batches: list[RolloutBatch] = []
    for index in range(ceil(total_items / batch_size)):
        start = index * batch_size
        end = min(start + batch_size, total_items)
        batches.append(
            RolloutBatch(
                batch_number=index + 1,
                start_index=start,
                end_index=end,
            )
        )
    return batches
