from __future__ import annotations

from grading.algorithms.readiness_blockers import ReadinessBlocker, blocker_codes


class ReadinessStatus:
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"
    COMPILED = "compiled"
    PARTIAL = "partial"
    BLOCKED = "blocked"
    STALE = "stale"
    FAILED = "failed"
    NEEDS_CORRECTION = "needs_correction"
    NEEDS_MODERATION = "needs_moderation"
    READY_FOR_HOD_REVIEW = "ready_for_hod_review"
    READY_FOR_ACADEMIC_REVIEW = "ready_for_academic_review"
    READY_FOR_PRINCIPAL_REVIEW = "ready_for_principal_review"
    READY_FOR_REPORTS = "ready_for_reports"
    NOT_READY_FOR_REPORTS = "not_ready_for_reports"


def determine_readiness_status(
    *,
    compilation_status: str | None,
    blockers: list[ReadinessBlocker],
    has_submitted_batch: bool,
    has_draft: bool,
) -> str:
    codes = blocker_codes(blockers)
    if "failed_compilation" in codes or compilation_status == "failed":
        return ReadinessStatus.FAILED
    if "stale_compilation" in codes or compilation_status == "stale":
        return ReadinessStatus.STALE
    if "correction_pending" in codes:
        return ReadinessStatus.NEEDS_CORRECTION
    if "missing_required_component" in codes:
        return ReadinessStatus.BLOCKED
    if "missing_marks" in codes or compilation_status == "partial":
        return ReadinessStatus.PARTIAL
    if any(code.startswith("cct_") for code in codes):
        return ReadinessStatus.NOT_READY_FOR_REPORTS
    if "no_compilation" in codes:
        if has_submitted_batch:
            return ReadinessStatus.SUBMITTED
        if has_draft:
            return ReadinessStatus.IN_PROGRESS
        return ReadinessStatus.NOT_STARTED
    if blockers:
        return ReadinessStatus.NOT_READY_FOR_REPORTS
    if compilation_status == "complete":
        return ReadinessStatus.READY_FOR_REPORTS
    return ReadinessStatus.NOT_READY_FOR_REPORTS
