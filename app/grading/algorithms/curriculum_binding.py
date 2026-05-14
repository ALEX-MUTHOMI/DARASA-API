"""Deterministic CBE/CCT binding checks for grading assessments.

The grading layer must consume curriculum truth from CCT instead of inventing
or re-resolving curriculum rules during mark entry.  These helpers stay
side-effect-free: callers pass already-known facts, and the algorithm returns a
sanitized result that can be used by models, selectors, and policies.
"""

from __future__ import annotations

from dataclasses import dataclass


DRAFT_STATUS = "draft"
OPERATIONAL_STATUSES = frozenset(
    {
        "open",
        "locked",
        "submitted",
        "approved",
        "archived",
    }
)


@dataclass(frozen=True)
class CurriculumBindingResult:
    is_bound: bool
    reason: str = ""


def assessment_status_requires_binding(status: str | None) -> bool:
    """Return whether a status is operational enough to require CCT context.

    Unknown statuses fail closed by requiring binding.  That prevents new
    lifecycle states from silently becoming grade-entry states.
    """

    if status == DRAFT_STATUS:
        return False
    return status in OPERATIONAL_STATUSES or status not in {DRAFT_STATUS}


def validate_curriculum_binding(
    *,
    status: str | None,
    curriculum_version_id: object | None,
    learning_area_id: object | None,
    rubric_foundation_id: object | None,
    curriculum_version_is_active: bool,
    has_active_publication: bool,
    rubric_matches_context: bool,
    require_locked_binding: bool = False,
    binding_locked: bool = False,
) -> CurriculumBindingResult:
    """Validate that an assessment can be used operationally for grading."""

    if not assessment_status_requires_binding(status):
        return CurriculumBindingResult(True)
    if curriculum_version_id is None:
        return CurriculumBindingResult(False, "curriculum_version_required")
    if learning_area_id is None:
        return CurriculumBindingResult(False, "learning_area_required")
    if rubric_foundation_id is None:
        return CurriculumBindingResult(False, "rubric_foundation_required")
    if not curriculum_version_is_active:
        return CurriculumBindingResult(False, "curriculum_version_inactive")
    if not has_active_publication:
        return CurriculumBindingResult(False, "curriculum_version_unpublished")
    if not rubric_matches_context:
        return CurriculumBindingResult(False, "rubric_context_mismatch")
    if require_locked_binding and not binding_locked:
        return CurriculumBindingResult(False, "curriculum_binding_unlocked")
    return CurriculumBindingResult(True)
