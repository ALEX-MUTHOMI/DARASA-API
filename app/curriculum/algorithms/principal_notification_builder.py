from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from django.core.exceptions import ValidationError

from curriculum.algorithms.pii_guard import validate_governance_text


NO_AUTO_MUTATION_NOTICE = (
    "Darasa has not automatically changed your school records. "
    "Principal review and school activation are required."
)


def build_notification_payload(
    *,
    authority_name: str,
    source_reference: str,
    checksum: str,
    review_status: str,
    impact_summary: str,
    required_action: str,
) -> Mapping[str, Any]:
    if review_status not in {"verified", "approved"}:
        raise ValidationError({"review_status": "Verified evidence is required."})
    for value in [impact_summary, required_action, source_reference]:
        validate_governance_text(value)
    evidence_summary = (
        f"Authority: {authority_name}; Source: {source_reference}; "
        f"Checksum: {checksum or 'recorded in source registry'}."
    )
    return {
        "title": "Senior School Regulatory Update Detected",
        "summary": f"{impact_summary} {NO_AUTO_MUTATION_NOTICE}",
        "evidence_summary": evidence_summary,
        "required_action": required_action,
    }
