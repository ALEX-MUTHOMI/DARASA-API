"""Deterministic transition rules for submitted-mark correction workflows."""

from __future__ import annotations

from dataclasses import dataclass


TRANSITIONS = {
    "draft": {"submitted", "cancelled"},
    "requested": {"under_hod_review", "approved_by_hod", "rejected_by_hod"},
    "submitted": {"under_hod_review", "cancelled"},
    "under_hod_review": {
        "approved_by_hod",
        "rejected_by_hod",
        "escalation_requested",
    },
    "approved": {"applied"},
    "approved_by_hod": {"applied"},
    "rejected": set(),
    "rejected_by_hod": set(),
    "escalation_requested": {
        "under_academic_head_review",
        "approved_by_academic_head",
        "rejected_by_academic_head",
    },
    "under_academic_head_review": {
        "approved_by_academic_head",
        "rejected_by_academic_head",
    },
    "approved_by_academic_head": {"applied"},
    "rejected_by_academic_head": set(),
    "applied": set(),
    "cancelled": set(),
    "expired": set(),
}


@dataclass(frozen=True)
class TransitionDecision:
    allowed: bool
    reason: str


def can_transition_correction(
    *,
    current_status: str,
    target_status: str,
) -> TransitionDecision:
    allowed = target_status in TRANSITIONS.get(current_status, set())
    if allowed:
        return TransitionDecision(allowed=True, reason="allowed")
    return TransitionDecision(allowed=False, reason="invalid_transition")
