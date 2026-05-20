"""Fail-closed HOD escalation rules."""

from __future__ import annotations

from dataclasses import dataclass


ESCALATION_ELIGIBLE_STATUSES = frozenset(
    {
        "requested",
        "submitted",
        "under_hod_review",
    }
)


@dataclass(frozen=True)
class EscalationDecision:
    allowed: bool
    reason: str


def can_escalate_hod_unavailable(
    *,
    status: str,
    explicit_reason: str,
    hod_available: bool = False,
) -> EscalationDecision:
    if status not in ESCALATION_ELIGIBLE_STATUSES:
        return EscalationDecision(False, "status_not_escalation_eligible")
    if hod_available:
        return EscalationDecision(False, "hod_available")
    if not explicit_reason.strip():
        return EscalationDecision(False, "reason_required")
    return EscalationDecision(True, "allowed")
