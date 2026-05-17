"""Deterministic rollback planning decisions for CCT."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RollbackDecision:
    status: str
    requires_review: bool
    reason: str


def plan_assessment_rebind_eligibility(
    *,
    has_submitted_batches: bool,
    has_grade_records: bool,
) -> RollbackDecision:
    if has_submitted_batches or has_grade_records:
        return RollbackDecision(
            status="review_required",
            requires_review=True,
            reason="submitted_academic_history_present",
        )
    return RollbackDecision(
        status="eligible_for_controlled_rebind",
        requires_review=False,
        reason="no_submitted_academic_history",
    )
