"""Correction status groupings for Phase 6E workflows."""

from __future__ import annotations


DRAFT_STATUSES = frozenset({"draft"})

HOD_REVIEW_STATUSES = frozenset(
    {
        "requested",
        "submitted",
        "under_hod_review",
    }
)

ACADEMIC_HEAD_REVIEW_STATUSES = frozenset(
    {
        "escalation_requested",
        "under_academic_head_review",
    }
)

APPROVED_UNAPPLIED_STATUSES = frozenset(
    {
        "approved",
        "approved_by_hod",
        "approved_by_academic_head",
    }
)

BLOCKING_CORRECTION_STATUSES = frozenset(
    {
        "requested",
        "submitted",
        "under_hod_review",
        "approved",
        "approved_by_hod",
        "escalation_requested",
        "under_academic_head_review",
        "approved_by_academic_head",
    }
)

TERMINAL_STATUSES = frozenset(
    {
        "rejected",
        "rejected_by_hod",
        "rejected_by_academic_head",
        "applied",
        "cancelled",
        "expired",
    }
)


def is_blocking_correction_status(status: str) -> bool:
    return status in BLOCKING_CORRECTION_STATUSES


def is_approved_unapplied_status(status: str) -> bool:
    return status in APPROVED_UNAPPLIED_STATUSES
