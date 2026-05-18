from __future__ import annotations

from dataclasses import dataclass

from curriculum.algorithms.document_signal_validator import DocumentSignalReport


@dataclass(frozen=True)
class VerificationConfidence:
    score: int
    level: str
    recommended_next_action: str


def score_verification_confidence(
    *,
    signals: DocumentSignalReport,
    authority_known: bool,
    official_source_match_status: str,
    duplicate_signal_count: int,
) -> VerificationConfidence:
    score = 10
    if authority_known:
        score += 20
    if signals.reference_number_valid:
        score += 15
    if signals.publication_number_valid:
        score += 10
    if signals.publication_date_detected:
        score += 10
    if signals.effective_date_detected:
        score += 10
    if signals.stamp_signal:
        score += 5
    if signals.signature_signal:
        score += 5
    if signals.template_signal:
        score += 5
    if official_source_match_status == "matched":
        score += 30
    elif official_source_match_status == "unmatched":
        score -= 30
    if duplicate_signal_count:
        score += min(10, duplicate_signal_count)
    score -= 10 * len(signals.risk_flags)
    score = max(0, min(100, score))

    if official_source_match_status == "unmatched":
        return VerificationConfidence(score, "rejected", "reject")
    if score >= 85:
        return VerificationConfidence(
            score,
            "needs_governance_review",
            "ready_for_governance_review",
        )
    if score >= 70:
        return VerificationConfidence(score, "high", "escalate_to_governance")
    if score >= 45:
        return VerificationConfidence(score, "medium", "await_official_confirmation")
    return VerificationConfidence(score, "low", "request_more_evidence")
