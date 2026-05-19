from __future__ import annotations

from grading.algorithms.readiness_blockers import ReadinessBlocker, blocker


def cct_readiness_blockers(
    *,
    assessment_is_bound: bool,
    has_school_adoption: bool,
    curriculum_version_withdrawn: bool,
    rollback_plan_count: int = 0,
    app_impact_plan_count: int = 0,
) -> list[ReadinessBlocker]:
    blockers: list[ReadinessBlocker] = []
    if not assessment_is_bound:
        blockers.append(
            blocker(
                code="assessment_not_cbe_cct_bound",
                message="Assessment is not bound to CBE/CCT context.",
            )
        )
    if not has_school_adoption:
        blockers.append(
            blocker(
                code="cct_adoption_missing",
                message="School adoption for the assessment curriculum is missing.",
                scope="curriculum",
            )
        )
    if curriculum_version_withdrawn:
        blockers.append(
            blocker(
                code="cct_withdrawal_review_required",
                message="Curriculum withdrawal requires report-readiness review.",
                scope="curriculum",
            )
        )
    if rollback_plan_count > 0:
        blockers.append(
            blocker(
                code="cct_rollback_review_required",
                message="Curriculum rollback planning affects readiness review.",
                scope="curriculum",
            )
        )
    if app_impact_plan_count > 0:
        blockers.append(
            blocker(
                code="cct_app_impact_review_required",
                message="CCT app impact planning requires academic review.",
                scope="curriculum",
                severity="review",
            )
        )
    return blockers
