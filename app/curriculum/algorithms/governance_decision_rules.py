from __future__ import annotations

from django.core.exceptions import ValidationError


APPROVAL_REPORT_STATUSES = frozenset({"complete", "escalated"})


def validate_governance_decision(
    *,
    decision: str,
    report_status: str,
    reason: str = "",
) -> str:
    normalized = decision.strip().lower()
    allowed = {
        "pending",
        "approved_for_publication",
        "rejected",
        "requires_more_evidence",
        "escalated",
    }
    if normalized not in allowed:
        raise ValidationError({"decision": "Governance decision is not allowed."})
    if normalized == "approved_for_publication" and report_status not in (
        APPROVAL_REPORT_STATUSES
    ):
        raise ValidationError(
            {"verification_report": "Approval requires a completed report."}
        )
    if normalized in {"rejected", "requires_more_evidence", "escalated"}:
        if not reason or not reason.strip():
            raise ValidationError({"reason": "Governance decision reason required."})
    return normalized
