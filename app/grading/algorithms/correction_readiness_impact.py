"""Readiness blockers caused by Phase 6E corrections and schema binding."""

from __future__ import annotations

from typing import Any

from grading.algorithms.correction_status import is_approved_unapplied_status
from grading.algorithms.readiness_blockers import blocker
from grading.algorithms.school_grading_schema_validator import (
    is_internal_assessment_type,
)


def correction_readiness_blockers(*, corrections: list[Any]) -> list[dict[str, Any]]:
    blockers = []
    if corrections:
        blockers.append(
            blocker(
                code="correction_pending",
                message="Pending correction workflow items block report readiness.",
                scope="correction",
            )
        )
    has_approved_unapplied = any(
        is_approved_unapplied_status(correction.status)
        for correction in corrections
    )
    if has_approved_unapplied:
        blockers.append(
            blocker(
                code="approved_correction_unapplied",
                message="Approved correction must be applied before reports.",
                scope="correction",
            )
        )
    return blockers


def schema_readiness_blockers(
    *,
    assessment_type: str,
    requires_internal_schema: bool,
    schema_status: str | None,
) -> list[dict[str, Any]]:
    if not requires_internal_schema:
        return []
    if not is_internal_assessment_type(assessment_type):
        return []
    if schema_status is None:
        return [
            blocker(
                code="school_schema_missing",
                message="Internal assessment requires a school grading schema.",
                scope="schema",
            )
        ]
    if schema_status in {"deprecated", "retired", "draft"}:
        return [
            blocker(
                code="school_schema_not_active",
                message=(
                    "Internal assessment schema is not active for report readiness."
                ),
                scope="schema",
            )
        ]
    return []
